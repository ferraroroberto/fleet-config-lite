"""Deterministic half of the lite `/prompt-audit` (port of fleet-config#831 / #834).

The skill checks instruction files (CLAUDE.md, AGENTS.md, copilot-instructions.md,
global-instructions.md, .claude/rules/*.md, SKILL.md) against the vendors' current
prompting guidance. "The helper measures, the session judges": this module does
every exact step -- hashing fetched guides against their baselines, enumerating the
scan surface, counting lint hits, the skip-unchanged ledger, and the digest -- so no
number is ever invented by a model. It never fetches a page and never edits a file.

Self-contained on purpose (the fleet-config-lite contract): stdlib only, no import
from any `_lib`, host detected from `git remote get-url origin` (`gh` or `glab`).
The helpers are a deliberate near-duplicate of fleet-config's
`.claude/skills/prompt-audit/audit.py`; `rules.md` and `sources.toml` are
byte-identical copies of that repo's files.

Hard caps, enforced here rather than in prose:
  MAX_REPOS_PER_RUN      repos planned per run (`plan` picks, `digest`/`ledger-write` refuse more)
  MAX_FINDINGS_PER_FILE  violation/consider findings kept per file per run

Subcommands (line output uses the `KEY=value|...` protocol):

  host [--repo-path P]              HOST=github|gitlab|CLI=gh|glab|REPO=...
  sources                           SOURCE=<id>|url=...|baseline=<sha>|marker=...
  diff-source --id I --file F [--final-url U]
                                    VERDICT=unchanged|changed|new-guide|not-checked|...
  plan [--repo R]... [--rescan-all] REPOS=, PLAN=, SECTION=, HIT=, HITS=, DEFERRED= lines
  digest --run JSON                 digest markdown on stdout, DIGEST=status=... on stderr
  ledger-write --run JSON [--date D] [--dry-run]
  comment --body-file F [--dry-run]

Every write accepts `--dry-run`, which prints `ARGV=` for each state-changing
command it would have run and spawns none of them. Reads still run.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

SKILL_DIR = Path(__file__).resolve().parent
HOME_DIR = SKILL_DIR.parents[1]  # skills/prompt-audit -> the checkout root
SOURCES_TOML = SKILL_DIR / "sources.toml"
RULES_MD = SKILL_DIR / "rules.md"

MAX_REPOS_PER_RUN = 2
MAX_FINDINGS_PER_FILE = 5

KIND = "prompt-audit"
TITLE = "prompt-audit ledger"
LEDGER_LABEL = "audit-meta"
BLOCK_MARKER = "<!-- prompt-audit-ledger -->"
STAMP_PREFIX = "prompt-audit-digest"
GLOBAL_FILE = "global-instructions.md"  # neutral counterpart of fleet-config's global file
MASTER_REPO = "project-scaffolding"
LEDGER_CAP = 600
COMMENT_CHAR_CAP = 60000
NEUTRAL = "neutral"
VERDICTS = ("unchanged", "changed", "new-guide", "not-checked")
SIZE_CAPS = {"claude-md": ("lines", 200), "rules": ("lines", 200),
             "skill": ("body-lines", 500), "agents-md": ("bytes", 32768)}
ALWAYS_ON_KINDS = {"claude-md", "agents-md", "rules"}
_WORKTREE = re.compile(r"-wt-")

log = logging.getLogger("prompt-audit")


class CapError(ValueError):
    """A run asked for more than a hard cap allows."""


def emit(line: str) -> None:
    sys.stdout.write(line + "\n")


# ---- small pure helpers ---------------------------------------------------------

def sha12(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:12]


def clean(value: str) -> str:
    """A value safe inside a `KEY=value|...` line."""
    return re.sub(r"\s+", " ", value.replace("|", "/")).strip()


def rules_rubric(data: Optional[bytes] = None) -> str:
    """sha256 of `rules.md` with CRLF normalised -- the same rubric the private tool records."""
    raw = RULES_MD.read_bytes() if data is None else data
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


def load_toml(path: Path = SOURCES_TOML) -> dict:
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def frontmatter_field(text: str, name: str) -> Optional[str]:
    """The `<name>:` value of a `---` frontmatter block, or None."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    block = text[3:end] if end != -1 else text[3:]
    m = re.search(rf"^{re.escape(name)}:\s*(.+)$", block, re.MULTILINE)
    return m.group(1).strip() if m else None


_QUOTED = re.compile(r"\"[^\"]+\"")


def strip_quoted(description: str) -> str:
    return _QUOTED.sub(" ", description)


def prose_words(description: str) -> int:
    """Description word count with double-quoted trigger phrases excluded."""
    return len(strip_quoted(description).split())


# ---- freshness gate -------------------------------------------------------------

_DEFAULT_MODEL_LIST = r"including ((?:[^.]|\.\d)+)\."


def extract_marker(kind: str, text: str, cfg: dict) -> Optional[str]:
    """The source's version marker, "" for kind `none`, None when not extractable."""
    if kind == "none":
        return ""
    if kind == "model-list":
        m = re.search(cfg.get("marker_pattern") or _DEFAULT_MODEL_LIST, text)
        return clean(m.group(1)) if m else None
    if kind == "llms-txt-lines":
        pattern = cfg.get("marker_pattern")
        found = sorted(set(re.findall(pattern, text))) if pattern else []
        return ",".join(found) if found else None
    if kind == "latest-model-frontmatter":
        if not text.startswith("---"):
            return None
        end = text.find("\n---", 3)
        block = text[3:end] if end != -1 else ""
        key = re.escape(cfg.get("marker_key", "model"))
        m = re.search(rf"^\s*{key}:\s*(\S+)\s*$", block, re.MULTILINE)
        return m.group(1) if m else None
    raise ValueError(f"unknown marker_kind {kind!r}")


def diff_source(cfg: dict, data: Optional[bytes], final_url: Optional[str] = None) -> dict:
    """Verdict for one fetched source. No bytes -> `not-checked`, never `unchanged`."""
    kind = cfg.get("marker_kind", "none")
    if not data:
        return {"verdict": "not-checked", "sha": "unmeasured", "marker": "unmeasured",
                "reason": "fetched file missing or empty"}
    text = data.decode("utf-8", errors="replace")
    sha = sha12(data)
    marker = extract_marker(kind, text, cfg)
    shown = "unmeasured" if marker is None else (marker or "none")
    out = {"sha": sha, "marker": shown}
    baseline_sha = cfg.get("baseline_sha", "")
    baseline_marker = cfg.get("baseline_marker", "")
    expected_url = cfg.get("baseline_final_url")
    if final_url and expected_url and final_url != expected_url:
        return {**out, "verdict": "changed", "reason": f"redirect target moved to {final_url}"}
    if kind == "llms-txt-lines":
        if marker is None:
            return {**out, "verdict": "changed", "reason": "no guide lines found in the index"}
        now, before = set(marker.split(",")), set(filter(None, baseline_marker.split(",")))
        if now - before:
            return {**out, "verdict": "new-guide", "reason": "new guide lines: " + ",".join(sorted(now - before))}
        if before - now:
            return {**out, "verdict": "changed", "reason": "guide lines removed: " + ",".join(sorted(before - now))}
        moved = "index sha moved, guide lines identical" if sha != baseline_sha else "identical"
        return {**out, "verdict": "unchanged", "reason": moved}
    if kind == "latest-model-frontmatter" and marker != baseline_marker:
        return {**out, "verdict": "new-guide", "reason": f"flagship marker {baseline_marker} -> {shown}"}
    if sha != baseline_sha:
        reason = f"sha {baseline_sha} -> {sha}"
        if kind == "model-list" and marker != baseline_marker:
            reason += "; model list changed"
        return {**out, "verdict": "changed", "reason": reason}
    return {**out, "verdict": "unchanged", "reason": "identical"}


# ---- fleet + inventory ----------------------------------------------------------

def fleet_repos(home: Path) -> Dict[str, Path]:
    """Git repos beside the home checkout. Worktrees (`*-wt-*`, or a `.git` file) are excluded."""
    out: Dict[str, Path] = {}
    try:
        children = sorted(home.parent.iterdir())
    except OSError as exc:
        log.warning("cannot list %s: %s", home.parent, exc)
        children = []
    for d in children:
        try:
            if d.is_dir() and not _WORKTREE.search(d.name) and (d / ".git").is_dir():
                out[d.name] = d
        except OSError:
            continue
    out.setdefault(home.name, home)
    return out


@dataclass
class Entry:
    key: str          # fleet-root-relative posix path, e.g. my-repo/CLAUDE.md
    path: Path
    repo: str
    kind: str
    audience: str = NEUTRAL
    data: Optional[bytes] = None

    @property
    def sha(self) -> str:
        return sha12(self.data) if self.data is not None else "unmeasured"

    @property
    def text(self) -> str:
        return self.data.decode("utf-8", errors="replace") if self.data is not None else ""


def kind_of(relpath: str) -> Optional[str]:
    name = relpath.rsplit("/", 1)[-1]
    if name == "SKILL.md":
        return "skill"
    if "/.claude/rules/" in f"/{relpath}" and name.endswith(".md"):
        return "rules"
    if name.endswith("CLAUDE.md") or name in (GLOBAL_FILE, "copilot-instructions.md"):
        return "claude-md"
    if name == "AGENTS.md":
        return "agents-md"
    return None


def audience_of(entry: Entry, repo_dir: Path, audiences: Dict[str, dict]) -> str:
    for name, cfg in audiences.items():
        if any(fnmatch.fnmatch(entry.key, g) for g in cfg.get("path_globs", [])):
            return name
    base = entry.key.rsplit("/", 1)[-1]
    agents = repo_dir / "AGENTS.md"
    for name, cfg in audiences.items():
        if base in cfg.get("unpointed", []):
            try:
                pointed = agents.is_file() and base in agents.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pointed = False
            if not pointed:
                return name
    return NEUTRAL


def _read(path: Path) -> Optional[bytes]:
    try:
        return path.read_bytes()
    except OSError:
        return None


def inventory(repos: Dict[str, Path], audiences: Dict[str, dict], home_name: str) -> List[Entry]:
    """The scan surface in audit order, one entry per path.

    (1) the home repo's global instructions file, (2) the scaffolding master, (3) every
    repo's always-on files, (4) the home repo's `skills/` and each repo's project skills.
    """
    wanted: List[Tuple[str, Path]] = []
    home = repos.get(home_name)
    if home:
        wanted.append((home_name, home / GLOBAL_FILE))
    if MASTER_REPO in repos:
        wanted.append((MASTER_REPO, repos[MASTER_REPO] / "CLAUDE.md"))
    for name, d in sorted(repos.items()):
        wanted += [(name, d / "CLAUDE.md"), (name, d / "AGENTS.md"), (name, d / ".github" / "copilot-instructions.md")]
        wanted += [(name, p) for p in sorted((d / ".claude" / "rules").glob("*.md"))]
    if home:
        wanted += [(home_name, p) for p in sorted((home / "skills").glob("*/SKILL.md"))]
    for name, d in sorted(repos.items()):
        for tier in (".claude/skills", ".github/skills"):
            wanted += [(name, p) for p in sorted((d / tier).glob("*/SKILL.md"))]

    seen, out = set(), []
    for name, path in wanted:
        if not path.is_file():
            continue
        rel = path.relative_to(repos[name]).as_posix()
        key, kind = f"{name}/{rel}", kind_of(rel)
        if key in seen or kind is None:
            continue
        seen.add(key)
        entry = Entry(key=key, path=path, repo=name, kind=kind, data=_read(path))
        entry.audience = audience_of(entry, repos[name], audiences)
        out.append(entry)
    return out


_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCE = re.compile(r"^\s*(```|~~~)")


def sections(text: str, file_audience: str, audiences: Dict[str, dict]) -> List[dict]:
    """Heading sections whose audience differs from the file's (marker-scoped)."""
    lines = text.splitlines()
    heads, in_fence = [], False
    for i, line in enumerate(lines, start=1):
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        m = None if in_fence else _HEADING.match(line)
        if m:
            heads.append((i, len(m.group(1)), m.group(2).strip()))
    out = []
    for idx, (start, level, heading) in enumerate(heads):
        aud = next((n for n, c in audiences.items() if any(mk in heading for mk in c.get("markers", []))), None)
        if not aud or aud == file_audience:
            continue
        end = next((nxt - 1 for nxt, nlevel, _ in heads[idx + 1:] if nlevel <= level), len(lines))
        out.append({"start": start, "end": end, "audience": aud, "heading": heading})
    return out


def audience_at(line_no: int, file_audience: str, secs: List[dict]) -> str:
    inner = [s for s in secs if s["start"] <= line_no <= s["end"]]
    return max(inner, key=lambda s: s["start"])["audience"] if inner else file_audience


# ---- rules + lint ---------------------------------------------------------------

_RULE_HEAD = re.compile(r"^### (R-\d{2}) (.+?)\s+tags:\s*(.+)$")


def parse_rules(text: str) -> Dict[str, dict]:
    rules: Dict[str, dict] = {}
    for line in text.splitlines():
        m = _RULE_HEAD.match(line)
        if m:
            tags = re.findall(r"\[([^\]]+)\]", m.group(3))
            plain = [t for t in tags if ":" not in t]
            kv = dict(t.split(":", 1) for t in tags if ":" in t)
            rules[m.group(1)] = {"id": m.group(1), "title": m.group(2).strip(),
                                 "vendor": plain[0].strip() if plain else "",
                                 "file": kv.get("file", "any").strip(), "tier": kv.get("tier", "").strip()}
    return rules


def rule_applies_to_kind(rule: dict, kind: str) -> bool:
    scope = rule.get("file", "any")
    return scope == "any" or (kind in ALWAYS_ON_KINDS if scope == "claude-md" else scope == kind)


def verdict_cap(vendor_tag: str, audience: str, audiences: Dict[str, dict]) -> Optional[str]:
    """Strongest verdict a rule can reach for a reader; None = does not apply."""
    if vendor_tag == "shared":
        return "violation"
    if vendor_tag == "conflict":
        return "violation" if audience == NEUTRAL else None
    if audience == NEUTRAL:
        return "consider"
    return "violation" if audiences.get(audience, {}).get("vendor") == vendor_tag else None


_INLINE_CODE = re.compile(r"`[^`\n]*`")
_MONTHS = "january|february|march|april|may|june|july|august|september|october|november|december"
PATTERNS: Dict[str, List[re.Pattern]] = {
    "R-01": [re.compile(r"\b(?:MUST|NEVER|ALWAYS|CRITICAL|IMPORTANT|REQUIRED|MANDATORY|NOT|DON'T)\b")],
    "R-02": [re.compile(r"\b(?:if|when) in doubt\b|\bdefault to (?:using|calling|running|invoking)\b", re.I)],
    "R-03": [re.compile(r"\bdouble[- ]check|\bre-?verify\b|\bverify your (?:answer|work|output|response|changes)\b"
                        r"|\bfinal verification step\b|\bsubagent to verify\b|\bre-?check your\b", re.I)],
    "R-04": [re.compile(r"\bevery\s+(?:\d+|few|couple of)\s+tool[- ]calls?\b"
                        r"|\bafter every\s+\d+\s+(?:tool[- ]calls?|steps)\b", re.I)],
    "R-05": [re.compile(r"\bhold (?:all |every |any )?(?:findings|results|updates|output)\s+"
                        r"(?:for|until)\s+(?:the\s+)?(?:final|end)\b", re.I)],
    "R-07": [re.compile(r"\bthink step[- ]by[- ]step\b|\bstep[- ]by[- ]step (?:reasoning|thinking)\b"
                        r"|\breason step[- ]by[- ]step\b", re.I),
             re.compile(r"^\s*\d+[.)]\s+(?:think|reason|reflect)\b", re.I)],
    "R-08": [re.compile(r"\b(?:do not|don't|never)\s+(?:think|reason)\b(?!\s+(?:about|of|that)\b)", re.I)],
    "R-09": [re.compile(r"\bonly report (?:high|critical)[- ]severity\b|\bbe conservative\b"
                        r"|\b(?:do not|don't) nitpick\b", re.I)],
    "R-10": [re.compile(r"\bprefill(?:ed|s|ing)?\b|\bbudget_tokens\b", re.I)],
    "R-11": [re.compile(rf"\b(?:before|after|until|since|as of|by)\s+(?:{_MONTHS})\s+\d{{4}}\b", re.I)],
    "R-12": [re.compile(r"\b(?:outline|present|share|state|write)\s+(?:a|an|your)\s+(?:upfront\s+)?plan\s+before\b"
                        r"|\bupfront plan\b|\bbegin (?:each|every) (?:response|turn) with a plan\b", re.I)],
}
LINE_PATTERNS: Dict[str, re.Pattern] = {
    "R-06": re.compile(r"\b(?:do not|don't|never|avoid|no)\s+(?:use\s+|using\s+)?"
                       r"(?:markdown|bullet(?:s| points)?|headers|headings|bold|lists|formatting)\b", re.I),
    "R-13": re.compile(r"\b(?:never|do not|don't|avoid|must not|mustn't)\b", re.I),
}
_MODAL = re.compile(r"\b(always|must not|must|never|do not|don't)\s+([a-z][a-z-]*(?:\s+[a-z][a-z-]*){0,2})", re.I)
_PERSON = re.compile(r"\bI\b(?!/)|\b(?i:me|my|we|our|you|your)\b")


def audience_terms(audience_cfg: dict) -> re.Pattern:
    terms = audience_cfg.get("terms", [])
    return re.compile("|".join(rf"\b{re.escape(t)}\b" for t in terms) if terms else r"(?!)")


@dataclass
class Hit:
    rule: str
    line: int
    count: int
    text: str
    cap: str = "violation"


@dataclass
class LintResult:
    entry: Entry
    lines: int
    hits: List[Hit] = field(default_factory=list)
    neg: Tuple[int, int] = (0, 0)
    desc_words: str = "n/a"
    size: str = ""

    def counts(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for h in self.hits:
            out[h.rule] = out.get(h.rule, 0) + h.count
        return dict(sorted(out.items()))


def body_start(text: str) -> int:
    """1-based line number where a frontmatter-bearing file's body begins."""
    if not text.startswith("---"):
        return 1
    lines = text.splitlines()
    return next((i + 2 for i in range(1, len(lines)) if lines[i].rstrip() == "---"), 1)


def instruction_lines(text: str) -> List[Tuple[int, str]]:
    """(line number, text) for lintable prose: no frontmatter, fences or inline code."""
    out, in_fence, start = [], False, body_start(text)
    for i, raw in enumerate(text.splitlines(), start=1):
        if i < start:
            continue
        if _FENCE.match(raw):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append((i, _INLINE_CODE.sub(" ", raw)))
    return out


def lint_entry(entry: Entry, rules: Dict[str, dict], audiences: Dict[str, dict]) -> LintResult:
    text = entry.text
    raw_lines = text.splitlines()
    res = LintResult(entry=entry, lines=len(raw_lines))
    secs = sections(text, entry.audience, audiences)
    lines = instruction_lines(text)

    def add(rule_id: str, line_no: int, count: int, excerpt: str) -> None:
        rule = rules.get(rule_id)
        if rule is None or not rule_applies_to_kind(rule, entry.kind):
            return
        cap = verdict_cap(rule["vendor"], audience_at(line_no, entry.audience, secs), audiences)
        if cap is not None:
            res.hits.append(Hit(rule_id, line_no, count, clean(excerpt)[:120], cap))

    instr = negative = 0
    for n, line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        for rule_id, pats in PATTERNS.items():
            count = sum(len(p.findall(line)) for p in pats)
            if count:
                add(rule_id, n, count, raw_lines[n - 1])
        if _HEADING.match(stripped):
            continue
        instr += 1
        negative += bool(LINE_PATTERNS["R-13"].search(line))
        for rule_id, pat in LINE_PATTERNS.items():
            if pat.search(line):
                add(rule_id, n, 1, raw_lines[n - 1])
    res.neg = (negative, instr)

    unit, limit = SIZE_CAPS[entry.kind]
    size = {"lines": len(raw_lines), "body-lines": len(raw_lines) - body_start(text) + 1}.get(unit, len(entry.data or b""))
    res.size = f"{size}{'b' if unit == 'bytes' else 'l'}/{limit}"
    if size > limit:
        add("R-14", 1, 1, f"{unit} {size} over cap {limit}")

    if entry.kind == "skill":
        desc = frontmatter_field(text, "description") or ""
        if desc:
            res.desc_words = str(prose_words(desc))
            if len(desc) > 1024:
                add("R-15", 1, 1, f"description {len(desc)} chars over 1024")
            person = len(_PERSON.findall(strip_quoted(desc)))
            if person:
                add("R-15", 1, person, f"description: {strip_quoted(desc)}")
        else:
            res.desc_words = "unmeasured"

    polarity: Dict[str, Dict[str, int]] = {}
    for n, line in lines:
        for modal, phrase in _MODAL.findall(line):
            sign = "+" if modal.lower() in ("always", "must") else "-"
            polarity.setdefault(phrase.lower(), {}).setdefault(sign, n)
    for _phrase, signs in sorted(polarity.items()):
        if len(signs) == 2:
            first = min(signs.values())
            add("R-16", first, 1, raw_lines[first - 1])

    all_markers = [mk for c in audiences.values() for mk in c.get("markers", [])]
    para: List[Tuple[int, str]] = []
    for n, line in lines + [(0, "")]:
        if line.strip():
            para.append((n, line))
            continue
        if para and audience_at(para[0][0], entry.audience, secs) == NEUTRAL:
            joined = " ".join(l for _, l in para)
            named = [a for a, c in audiences.items() if audience_terms(c).search(joined)]
            if len(named) == 1 and not any(mk in joined for mk in all_markers):
                terms = audience_terms(audiences[named[0]])
                anchor = next((m for m, l in para if terms.search(l)), para[0][0])
                add("R-17", anchor, 1, raw_lines[anchor - 1])
        para = []
    res.hits.sort(key=lambda h: (h.line, h.rule))
    return res


# ---- ledger ---------------------------------------------------------------------

_ENTRY_RE = re.compile(r"^([^:#\s<][^:]*?):[ \t]*([0-9a-f]{12})[ \t]*$", re.MULTILINE)
_MARKER_RE = re.compile(r"^[ \t]*<!--[ \t]*audit-managed:[ \t]*kind=([\w-]+)[ \t]*-->[ \t]*$", re.MULTILINE)


def marker_for(kind: str) -> str:
    return f"<!-- audit-managed: kind={kind} -->"


def has_marker(body: str, kind: str) -> bool:
    """True only when the marker is the body's first line (quoting it in prose does not count)."""
    m = _MARKER_RE.match((body or "").lstrip())
    return bool(m) and m.group(1) == kind


def ensure_marker(body: str, kind: str) -> str:
    stripped = _MARKER_RE.sub("", body or "").lstrip("\n")
    return f"{marker_for(kind)}\n\n{stripped}" if stripped else f"{marker_for(kind)}\n"


def pick_ledger(issues: List[dict]) -> Tuple[Optional[int], List[int]]:
    """(issue to keep, strays): marker or exact title, lowest number wins."""
    found = sorted(i["number"] for i in issues
                   if has_marker(i.get("body", ""), KIND) or (i.get("title") or "").strip() == TITLE)
    return (found[0], found[1:]) if found else (None, [])


def parse_ledger(body: str) -> dict:
    body = (body or "").replace("\r\n", "\n")
    idx = body.find(BLOCK_MARKER)
    if idx == -1:
        return {"rubric": None, "run_at": None, "files": {}}
    block = body[idx:]
    end = block.find("-->", len(BLOCK_MARKER))
    block = block[:end] if end != -1 else block
    rub = re.search(r"^rubric-sha:[ \t]*([0-9a-f]+)[ \t]*$", block, re.MULTILINE)
    at = re.search(r"^last-run-at:[ \t]*(\S+)[ \t]*$", block, re.MULTILINE)
    return {"rubric": rub.group(1) if rub else None, "run_at": at.group(1) if at else None,
            "files": {m.group(1).strip(): m.group(2) for m in _ENTRY_RE.finditer(block)}}


def plan_scan(current: Dict[str, str], ledger: dict, rubric: str, rescan_all: bool = False) -> Dict[str, Tuple[str, str]]:
    plan = {}
    for key, sha in sorted(current.items()):
        if sha == "unmeasured":
            plan[key] = ("unmeasured", "unreadable")
        elif rescan_all:
            plan[key] = ("scan", "rescan-all")
        elif not ledger.get("rubric"):
            plan[key] = ("scan", "no-ledger")
        elif ledger["rubric"] != rubric:
            plan[key] = ("scan", "rubric-changed")
        elif key not in ledger["files"]:
            plan[key] = ("scan", "new")
        elif ledger["files"][key] != sha:
            plan[key] = ("scan", "changed")
        else:
            plan[key] = ("skip", "unchanged")
    return plan


def select_repos(entries: List[Entry], plan: Dict[str, Tuple[str, str]], requested: Optional[List[str]] = None,
                 cap: int = MAX_REPOS_PER_RUN) -> Tuple[List[str], Dict[str, int]]:
    """(repos this run, {deferred repo: files it would scan}) -- never more than `cap` repos.

    Explicit `requested` repos over the cap raise CapError. Otherwise the first repos in
    audit order with anything to scan are taken; the rest wait for a later run, so the
    ledger rotates through the fleet two repos at a time.
    """
    order = list(dict.fromkeys(e.repo for e in entries))
    pending = {r: sum(1 for e in entries if e.repo == r and plan[e.key][0] != "skip") for r in order}
    if requested:
        requested = list(dict.fromkeys(requested))
        if len(requested) > cap:
            raise CapError(f"{len(requested)} repos requested; the cap is {cap} per run")
        chosen = requested
    else:
        chosen = [r for r in order if pending[r]][:cap]
    return chosen, {r: n for r, n in pending.items() if n and r not in chosen}


def merge_ledger(ledger: dict, recorded: Dict[str, str], rubric: str) -> Tuple[Dict[str, str], int]:
    """New entries; prior entries survive only under the same rubric. Returns (files, dropped)."""
    base = dict(ledger["files"]) if ledger.get("rubric") == rubric else {}
    base.update(recorded)
    keys = sorted(base)
    return {k: base[k] for k in keys[:LEDGER_CAP]}, max(0, len(keys) - LEDGER_CAP)


def render_ledger_body(files: Dict[str, str], rubric: str, run_at: str,
                       sources: Dict[str, dict], dropped: int = 0) -> str:
    """The ledger body. The hidden block is byte-for-byte the private tool's format."""
    rows = [f"| `{sid}` | {c.get('vendor', '')} | {c.get('role', '')} | `{c.get('baseline_sha', '')}` "
            f"| {clean(str(c.get('baseline_marker') or '-'))} | {c.get('baseline_date', '')} |"
            for sid, c in sources.items()]
    lines = [
        "Standing ledger for `/prompt-audit` (fleet-config-lite port of fleet-config#831) - vendor-guide baselines "
        "plus the skip-unchanged file table. Managed by `skills/prompt-audit/audit.py`; do not hand-edit the block. "
        "The last comment is the current state of the audit.",
        "",
        "## Guide baselines (`sources.toml`)",
        "",
        "| source | vendor | role | baseline sha | marker | date |",
        "|---|---|---|---|---|---|",
        *rows,
        "",
        f"## Assessed files ({len(files)}{f', {dropped} over the cap - rescanned next run' if dropped else ''})",
        "",
        BLOCK_MARKER,
        "<!--",
        f"last-run-at: {run_at}",
        f"rubric-sha: {rubric}",
        *[f"{k}: {v}" for k, v in sorted(files.items())],
        "-->",
        "",
        f"rubric-sha `{rubric[:12]}` - last run {run_at} - {len(files)} file hashes recorded (hidden block above).",
    ]
    return "\n".join(lines) + "\n"


# ---- digest ---------------------------------------------------------------------

def _kv(line: str) -> dict:
    head, _, rest = line.partition("|")
    key, _, value = head.partition("=")
    out = {key: value}
    for part in rest.split("|"):
        k, sep, v = part.partition("=")
        if sep:
            out[k] = v
    return out


def run_repos(run: dict) -> List[str]:
    """Repos a run touched, from its PLAN= lines. Over the cap raises CapError."""
    repos = sorted({_kv(l)["PLAN"].split("/", 1)[0] for l in run.get("plan", []) if l.startswith("PLAN=")})
    if len(repos) > MAX_REPOS_PER_RUN:
        raise CapError(f"run covers {len(repos)} repos ({', '.join(repos)}); the cap is {MAX_REPOS_PER_RUN}")
    return repos


def cap_findings(findings: List[dict], cap: int = MAX_FINDINGS_PER_FILE) -> Tuple[List[dict], int]:
    """At most `cap` violation/consider findings for one file, violations first. Returns (kept, dropped)."""
    reportable = [f for f in findings if f.get("verdict") in ("violation", "consider")]
    ordered = sorted(reportable, key=lambda f: (f["verdict"] != "violation", f.get("line") or 0))
    return ordered[:cap], max(0, len(ordered) - cap)


def partition_run(run: dict) -> dict:
    """Split a run into judged, skipped, unmeasured and capped -- the one place counts come from.

    A planned-scan file with no judgment is unmeasured; a judged file with any
    `unmeasured` rule verdict is only partly established and is not recorded.
    """
    run_repos(run)
    plan = [_kv(l) for l in run.get("plan", []) if l.startswith("PLAN=")]
    sha_of = {p["PLAN"]: p.get("sha", "") for p in plan}
    scan = [p["PLAN"] for p in plan if p.get("action") == "scan"]
    unreadable = [p["PLAN"] for p in plan if p.get("action") == "unmeasured"]
    judgments = run.get("judgments") or {}
    scan_ran = bool(run.get("scan_ran"))
    judged = [k for k in scan if judgments.get(k) is not None] if scan_ran else []
    unmeasured_rules = [dict(f, path=k) for k in judged for f in judgments[k] if f.get("verdict") == "unmeasured"]
    partly = {f["path"] for f in unmeasured_rules}
    findings, capped = [], {}
    for k in judged:
        kept, dropped = cap_findings(judgments[k])
        findings += [dict(f, path=k) for f in kept]
        if dropped:
            capped[k] = dropped
    return {
        "plan": plan,
        "skip": [p["PLAN"] for p in plan if p.get("action") == "skip"],
        "judged": judged,
        "unmeasured": (unreadable + [k for k in scan if judgments.get(k) is None]) if scan_ran else [],
        "unmeasured_rules": unmeasured_rules,
        "findings": findings,
        "capped": capped,
        "recorded": {k: sha_of[k] for k in judged if k not in partly and sha_of.get(k) not in ("", "unmeasured")},
    }


_MARKUP = re.compile(r"^\s*(?:[-+*]|\d+[.)])\s+|[*_`>#]")


def norm_line(s: str) -> str:
    return re.sub(r"\s+", " ", _MARKUP.sub("", s)).strip().lower()


def render_digest(run: dict, rules: Dict[str, dict], master_text: str = "") -> Tuple[str, str]:
    """(markdown, status). Pure: every count comes from `partition_run`."""
    srcs = [_kv(l) for l in run.get("sources", [])]
    by_verdict = {v: [s for s in srcs if s.get("VERDICT") == v] for v in VERDICTS}
    stale = by_verdict["changed"] + by_verdict["new-guide"]
    guides = "changed" if stale else ("not-checked" if by_verdict["not-checked"] or not srcs else "unchanged")
    parts = partition_run(run)
    scan_ran = bool(run.get("scan_ran"))
    status = "partial" if parts["unmeasured"] or parts["unmeasured_rules"] else "complete"
    scan = "dry-run" if run.get("dry_run") else ("posted" if scan_ran else "not-run")
    stamp = (f"<!-- {STAMP_PREFIX} run={run.get('date') or 'unknown'} status={status} scan={scan} "
             f"update-issue={run.get('update_issue') or 'none'} -->")
    out = [f"## prompt-audit digest - {run.get('date', '')}", stamp, "",
           f"`status={status}` - `guides={guides}` - `rubric={str(run.get('rubric', ''))[:12]}` - "
           f"`repos={','.join(run_repos(run)) or 'none'}`" + (" - **dry run, nothing written**" if run.get("dry_run") else ""), ""]
    out.append(f"**Guides:** {len(srcs)} sources - " + ", ".join(f"{v} {len(by_verdict[v])}" for v in VERDICTS))
    out += [f"- `{s.get('id')}` **{s.get('VERDICT')}** - {s.get('reason', '')}" for s in stale + by_verdict["not-checked"]]
    out.append("")
    if not scan_ran:
        out += ["**Scan:** not run - a guide moved past the vendored baseline. The rule-set is owned by "
                "fleet-config: re-vendor `rules.md` and `sources.toml` from there once it is updated, then rerun.", ""]
        return "\n".join(out) + "\n", status

    plan, skip, judged, findings = parts["plan"], parts["skip"], parts["judged"], parts["findings"]
    out.append(f"**Scan:** {len(plan)} files - scanned {len(judged)}, skipped {len(skip)} (unchanged), "
               f"unmeasured {len(parts['unmeasured'])}, rule verdicts not established {len(parts['unmeasured_rules'])}")
    deferred = [_kv(l) for l in run.get("deferred", []) if l.startswith("DEFERRED=")]
    if deferred:
        out.append(f"**Deferred by the {MAX_REPOS_PER_RUN}-repo cap:** "
                   + ", ".join(f"{d['DEFERRED']} ({d.get('scan', '?')} files)" for d in deferred))
    tally: Dict[str, Dict[str, int]] = {}
    for f in findings:
        tally.setdefault(f["rule"], {"violation": 0, "consider": 0})[f["verdict"]] += 1
    out += ["", f"**Findings in scanned files:** {sum(t['violation'] for t in tally.values())} violation, "
                f"{sum(t['consider'] for t in tally.values())} consider, across {len({f['path'] for f in findings})} files", ""]
    if tally:
        out += ["| rule | violation | consider |", "|---|---|---|"]
        out += [f"| {r} {rules.get(r, {}).get('title', '')} | {t['violation']} | {t['consider']} |" for r, t in sorted(tally.items())]
        out.append("")
    master = {norm_line(l) for l in master_text.splitlines() if len(norm_line(l)) >= 20}
    master_key = f"{MASTER_REPO}/CLAUDE.md"
    shared: Dict[Tuple[str, str], dict] = {}
    local = []
    for f in findings:
        n = norm_line(f.get("text", ""))
        if f["path"] != master_key and len(n) >= 20 and n in master:
            g = shared.setdefault((f["rule"], n), dict(f, repos=set()))
            g["repos"].add(f["path"].split("/", 1)[0])
            if f["verdict"] == "violation":
                g["verdict"] = "violation"
        else:
            local.append(f)
    if shared:
        out += ["### Shared with the scaffolding master (fix once there)", ""]
        out += [f"- **{f['rule']}** {f['verdict']} - `{clean(f.get('text', ''))[:100]}` - propagate to: "
                f"{', '.join(sorted(f['repos']))}" for f in shared.values()] + [""]
    if local:
        out += ["### Findings", ""]
        for f in local:
            where = f"{f['path']}:{f['line']}" if f.get("line") else f["path"]
            out.append(f"- `{where}` **{f['rule']}** {f['verdict']} - {clean(f.get('note') or f.get('text', ''))[:160]}")
        out.append("")
    if parts["capped"]:
        out += [f"### Held back by the {MAX_FINDINGS_PER_FILE}-findings-per-file cap", ""]
        out += [f"- `{k}`: {n} more (the file's next change buys a rescan)" for k, n in sorted(parts["capped"].items())] + [""]
    if parts["unmeasured"]:
        out += ["### Unmeasured (not established - not compliant)", ""] + [f"- `{k}`" for k in parts["unmeasured"]] + [""]
    if parts["unmeasured_rules"]:
        out += ["### Rules not established (rescanned next run)", ""]
        out += [f"- `{f['path']}` **{f['rule']}** - {clean(f.get('note', ''))[:160]}" for f in parts["unmeasured_rules"]] + [""]
    if skip:
        out += [f"<details><summary>Skipped - unchanged since the last scan under this rubric ({len(skip)})</summary>", ""]
        out += [f"- `{k}`" for k in skip] + ["", "</details>", ""]
    body = "\n".join(out) + "\n"
    if len(body) > COMMENT_CHAR_CAP:
        body = body[:COMMENT_CHAR_CAP] + "\n\n... digest truncated at the comment size cap.\n"
    return body, status


# ---- git / gh / glab plumbing ---------------------------------------------------

def _run(cmd: List[str], cwd: Optional[str] = None, timeout: int = 120) -> subprocess.CompletedProcess:
    """The one subprocess spawn in this module (tests stub it)."""
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, creationflags=NO_WINDOW)


def parse_owner_repo(remote_url: str) -> str:
    """'owner/repo' (GitLab subgroups keep their slashes) or '' if unparseable."""
    u = re.sub(r"\.git$", "", (remote_url or "").strip())
    if "://" in u:
        m = re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://[^/]+/(.+)$", u)
        path = m.group(1) if m else ""
    else:
        path = u.partition(":")[2]
    parts = [p for p in path.strip("/").split("/") if p]
    return "/".join(parts) if len(parts) >= 2 else ""


def detect_host(remote_url: str) -> str:
    return "github" if "github.com" in (remote_url or "") else "gitlab"


def cli_for(host: str) -> str:
    return "gh" if host == "github" else "glab"


def resolve_repo(repo_path: Path) -> Tuple[str, str]:
    """(host, owner/repo) from `git remote get-url origin`."""
    try:
        r = _run(["git", "remote", "get-url", "origin"], cwd=str(repo_path))
        url = r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        url = ""
    repo = parse_owner_repo(url)
    if not repo:
        raise SystemExit(f"cannot resolve owner/repo from the origin remote of {repo_path}")
    return detect_host(url), repo


def _cli(host: str, args: List[str]) -> str:
    cli = cli_for(host)
    try:
        r = _run([cli, *args])
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"{cli} {' '.join(args[:2])} failed: {exc}") from exc
    if r.returncode != 0:
        raise RuntimeError(f"{cli} {' '.join(args[:2])} exit {r.returncode}: {(r.stderr or '').strip()[:200]}")
    return (r.stdout or "").strip()


def _write(host: str, args: List[str], dry_run: bool) -> str:
    """A state-changing CLI call; under dry-run only its argv is printed."""
    if dry_run:
        emit("ARGV=" + subprocess.list2cmdline([cli_for(host), *args]))
        return ""
    return _cli(host, args)


def list_issues_args(host: str, repo: str, label: str) -> List[str]:
    if host == "github":
        return ["issue", "list", "--repo", repo, "--state", "all", "--label", label,
                "--limit", "300", "--json", "number,title,body,state"]
    return ["issue", "list", "--repo", repo, "--all", "--label", label, "--per-page", "100", "--output", "json"]


def list_issues(host: str, repo: str, label: str) -> List[dict]:
    """Issues carrying `label`, normalised to {number, title, body, state}."""
    out = _cli(host, list_issues_args(host, repo, label))
    data = json.loads(out) if out else []
    if host == "github":
        return [{**i, "state": (i.get("state") or "").lower()} for i in data]
    return [{"number": i.get("iid"), "title": i.get("title", ""), "body": i.get("description") or "",
             "state": "open" if i.get("state") == "opened" else "closed"} for i in data]


def read_ledger(host: str, repo: str) -> dict:
    """{number, rubric, run_at, files, error}. An unreadable ledger reads as empty plus `error`."""
    try:
        issues = [i for i in list_issues(host, repo, LEDGER_LABEL) if i["state"] == "open"]
    except (RuntimeError, ValueError) as exc:
        return {"number": None, "rubric": None, "run_at": None, "files": {}, "error": str(exc)}
    keep, strays = pick_ledger(issues)
    if strays:
        log.warning("extra prompt-audit ledger issues left untouched: %s", strays)
    body = next((i["body"] for i in issues if i["number"] == keep), "") if keep else ""
    return {"number": keep, **parse_ledger(body), "error": None}


def upsert_ledger(host: str, repo: str, number: Optional[int], body: str, dry_run: bool) -> str:
    """Create or edit the single ledger issue; never a second one."""
    fh = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8", newline="")
    fh.write(ensure_marker(body, KIND))
    fh.close()
    label_args = (["label", "create", LEDGER_LABEL, "--repo", repo] if host == "github"
                  else ["label", "create", "--repo", repo, "-n", LEDGER_LABEL])
    try:
        try:
            _write(host, label_args, dry_run)
        except RuntimeError:
            pass  # the label already exists
        if host == "github":
            if number is None:
                return _write(host, ["issue", "create", "--repo", repo, "--title", TITLE, "--body-file", fh.name,
                                     "--label", LEDGER_LABEL, "--assignee", "@me"], dry_run)
            _write(host, ["issue", "edit", str(number), "--repo", repo, "--title", TITLE, "--body-file", fh.name,
                          "--add-label", LEDGER_LABEL], dry_run)
            return f"#{number}"
        if number is None:
            out = _write(host, ["issue", "create", "--repo", repo, "--title", TITLE, "--description-file", fh.name,
                                "--label", LEDGER_LABEL, "--assignee", "@me", "--yes"], dry_run)
            return out.splitlines()[-1] if out else ""
        _write(host, ["issue", "update", str(number), "--repo", repo, "--title", TITLE,
                      "--description-file", fh.name, "--label", LEDGER_LABEL], dry_run)
        return f"#{number}"
    finally:
        os.unlink(fh.name)


def comment_args(host: str, repo: str, number: int, body_file: str) -> List[str]:
    if host == "github":
        return ["issue", "comment", str(number), "--repo", repo, "--body-file", body_file]
    return ["issue", "note", str(number), "--repo", repo, "--message-file", body_file]


# ---- subcommands ----------------------------------------------------------------

def _master_text(repos: Dict[str, Path]) -> str:
    master = repos.get(MASTER_REPO)
    return ((_read(master / "CLAUDE.md") if master else None) or b"").decode("utf-8", "replace")


def cmd_host(repo_path: Path) -> int:
    host, repo = resolve_repo(repo_path)
    emit(f"HOST={host}|CLI={cli_for(host)}|REPO={repo}")
    emit("LEDGER_READ_ARGV=" + subprocess.list2cmdline([cli_for(host), *list_issues_args(host, repo, LEDGER_LABEL)]))
    return 0


def cmd_sources(cfg: dict) -> int:
    for sid, s in cfg.get("sources", {}).items():
        emit(f"SOURCE={sid}|url={s['url']}|vendor={s.get('vendor', '')}|role={s.get('role', '')}"
             f"|marker_kind={s.get('marker_kind', 'none')}|baseline={s.get('baseline_sha', '')}"
             f"|marker={clean(str(s.get('baseline_marker') or 'none'))}")
    emit(f"SOURCES={len(cfg.get('sources', {}))}")
    return 0


def cmd_diff_source(cfg: dict, sid: str, file: str, final_url: Optional[str]) -> int:
    src = cfg.get("sources", {}).get(sid)
    if src is None:
        log.error("unknown source id %r - not in %s", sid, SOURCES_TOML.name)
        return 2
    p = Path(file)
    v = diff_source(src, _read(p) if p.is_file() else None, final_url)
    emit(f"VERDICT={v['verdict']}|id={sid}|sha={v['sha']}|marker={clean(v['marker'])}|reason={clean(v['reason'])}")
    return 0


def cmd_plan(home: Path, cfg: dict, requested: Optional[List[str]], rescan_all: bool) -> int:
    audiences = cfg.get("audiences", {})
    repos = fleet_repos(home)
    unknown = sorted(set(requested or []) - set(repos))
    if unknown:
        log.error("not a fleet repo beside %s: %s", home, ", ".join(unknown))
        return 2
    entries = inventory(repos, audiences, home.name)
    rubric = rules_rubric()
    host, slug = resolve_repo(home)
    ledger = read_ledger(host, slug)
    if ledger["error"]:
        log.warning("ledger unreadable, every file plans as a scan: %s", ledger["error"])
    plan = plan_scan({e.key: e.sha for e in entries}, ledger, rubric, rescan_all)
    try:
        chosen, deferred = select_repos(entries, plan, requested)
    except CapError as exc:
        log.error("%s", exc)
        return 2
    emit(f"REPOS={','.join(chosen) or 'none'}|cap={MAX_REPOS_PER_RUN}")
    rules = parse_rules(RULES_MD.read_text(encoding="utf-8"))
    counts = {"scan": 0, "skip": 0, "unmeasured": 0}
    for e in (e for e in entries if e.repo in chosen):
        action, reason = plan[e.key]
        counts[action] += 1
        emit(f"PLAN={e.key}|action={action}|reason={reason}|sha={e.sha}|audience={e.audience}|kind={e.kind}")
        if action != "scan":
            continue
        for s in sections(e.text, e.audience, audiences):
            emit(f"SECTION={e.key}#L{s['start']}-L{s['end']}|audience={s['audience']}|heading={clean(s['heading'])}")
        res = lint_entry(e, rules, audiences)
        for h in res.hits:
            emit(f"HIT={e.key}:{h.line}|rule={h.rule}|cap={h.cap}|count={h.count}|text={h.text}")
        hits = ",".join(f"{k}:{v}" for k, v in res.counts().items()) or "none"
        emit(f"HITS={e.key}|lines={res.lines}|size={res.size}|hits={hits}|neg={res.neg[0]}/{res.neg[1]}|desc_words={res.desc_words}")
    for repo, n in sorted(deferred.items()):
        emit(f"DEFERRED={repo}|scan={n}")
    state = "unreadable" if ledger["error"] else f"#{ledger['number'] or 'none'}"
    emit(f"LEDGER={state}|home={slug}|host={host}|rubric={rubric[:12]}|ledger_rubric={(ledger['rubric'] or 'none')[:12]}"
         f"|scan={counts['scan']}|skip={counts['skip']}|unmeasured={counts['unmeasured']}|deferred={len(deferred)}")
    return 0


def cmd_digest(home: Path, run_file: str) -> int:
    run = json.loads(Path(run_file).read_text(encoding="utf-8"))
    run.setdefault("rubric", rules_rubric())
    try:
        body, status = render_digest(run, parse_rules(RULES_MD.read_text(encoding="utf-8")), _master_text(fleet_repos(home)))
    except CapError as exc:
        log.error("%s", exc)
        return 2
    sys.stdout.write(body)
    sys.stderr.write(f"DIGEST=status={status}\n")
    return 0


def cmd_ledger_write(home: Path, cfg: dict, run_file: str, date: Optional[str], dry_run: bool) -> int:
    run = json.loads(Path(run_file).read_text(encoding="utf-8"))
    try:
        repos_in_run = run_repos(run)
    except CapError as exc:
        log.error("%s", exc)
        return 2
    repos = fleet_repos(home)
    surface = {e.key for e in inventory({r: p for r, p in repos.items() if r in repos_in_run or r == home.name},
                                        cfg.get("audiences", {}), home.name)}
    recorded = partition_run(run)["recorded"]
    outside = sorted(set(recorded) - surface)
    if outside:
        log.error("not in the scan surface: %s", ", ".join(outside))
        return 2
    host, slug = resolve_repo(home)
    ledger = read_ledger(host, slug)
    if ledger["error"]:
        if not dry_run:
            log.error("cannot read the ledger, refusing to write (a blind create could duplicate it): %s", ledger["error"])
            return 1
        log.warning("ledger unreadable under dry-run, showing a first-run create: %s", ledger["error"])
    rubric = rules_rubric()
    files, dropped = merge_ledger(ledger, recorded, rubric)
    body = render_ledger_body(files, rubric, date or dt.date.today().isoformat(), cfg.get("sources", {}), dropped)
    if dry_run:
        sys.stdout.write(body)
    try:
        url = upsert_ledger(host, slug, ledger["number"], body, dry_run)
    except RuntimeError as exc:
        log.error("%s", exc)
        return 1
    emit(f"LEDGER_WRITE={'dry-run' if dry_run else url}|recorded={len(recorded)}|entries={len(files)}|dropped={dropped}")
    return 0


def cmd_comment(home: Path, body_file: str, dry_run: bool) -> int:
    host, slug = resolve_repo(home)
    ledger = read_ledger(host, slug)
    if ledger["number"] is None:
        log.error("no prompt-audit ledger issue on %s yet - run `ledger-write` first (%s)", slug, ledger["error"] or "not found")
        return 2
    try:
        out = _write(host, comment_args(host, slug, ledger["number"], body_file), dry_run)
    except RuntimeError as exc:
        log.error("%s", exc)
        return 1
    emit(f"LEDGER_COMMENT={'dry-run' if dry_run else out}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stderr)
    ap = argparse.ArgumentParser(description="Deterministic half of the lite /prompt-audit.")
    ap.add_argument("--home-path", default=str(HOME_DIR), help="checkout whose origin holds the ledger (default: this repo)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("host")
    h.add_argument("--repo-path", default=None)
    sub.add_parser("sources")
    d = sub.add_parser("diff-source")
    d.add_argument("--id", required=True)
    d.add_argument("--file", required=True)
    d.add_argument("--final-url", default=None)
    p = sub.add_parser("plan")
    p.add_argument("--repo", action="append", default=None, help=f"repeatable, at most {MAX_REPOS_PER_RUN}")
    p.add_argument("--rescan-all", action="store_true")
    dg = sub.add_parser("digest")
    dg.add_argument("--run", required=True)
    lw = sub.add_parser("ledger-write")
    lw.add_argument("--run", required=True)
    lw.add_argument("--date", default=None)
    lw.add_argument("--dry-run", action="store_true")
    c = sub.add_parser("comment")
    c.add_argument("--body-file", required=True)
    c.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    home = Path(args.home_path).resolve()
    cfg = load_toml()
    if args.cmd == "host":
        return cmd_host(Path(args.repo_path).resolve() if args.repo_path else home)
    if args.cmd == "sources":
        return cmd_sources(cfg)
    if args.cmd == "diff-source":
        return cmd_diff_source(cfg, args.id, args.file, args.final_url)
    if args.cmd == "plan":
        return cmd_plan(home, cfg, args.repo, args.rescan_all)
    if args.cmd == "digest":
        return cmd_digest(home, args.run)
    if args.cmd == "ledger-write":
        return cmd_ledger_write(home, cfg, args.run, args.date, args.dry_run)
    return cmd_comment(home, args.body_file, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
