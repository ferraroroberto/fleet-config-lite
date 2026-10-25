"""Pure text layer of the prompt audit: heading sections, rule parsing and the deterministic lint.

Imported by `audit.py` from this folder. It never imports `audit.py`, so the entry point stays the
single path a `SKILL.md` invokes. No I/O, no subprocess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from audit import Entry

NEUTRAL = "neutral"
SIZE_CAPS = {"claude-md": ("lines", 200), "rules": ("lines", 200),
             "skill": ("body-lines", 500), "agents-md": ("bytes", 32768)}
ALWAYS_ON_KINDS = {"claude-md", "agents-md", "rules"}


def clean(value: str) -> str:
    """A value safe inside a `KEY=value|...` line."""
    return re.sub(r"\s+", " ", value.replace("|", "/")).strip()


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
