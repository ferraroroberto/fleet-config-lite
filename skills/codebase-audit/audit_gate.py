"""Deterministic gate + managed-issue upsert for the lite /codebase-audit.

Host-agnostic (GitHub `gh` or GitLab `glab`, detected from `git remote
get-url origin`), stdlib only, self-contained: the lite counterpart of
fleet-config's `skills/_lib/audit_issue.py`, minus everything that needs the
private fleet (GraphQL closing references, PR diff stats, worktree claims,
stray-collapsing, Slack). The ledger format is byte-compatible with the
private tool, so a repo audited by both shares one ledger issue.

Subcommands (all take `--repo-path`, default: the current directory):

  gate [--threshold N] [--no-fetch] [--dry-run]
        Prints one JSON line with `decision` in SKIP | SKIP_SELF_FIX |
        SKIP_BELOW_THRESHOLD | AUDIT plus the facts behind it. The only
        write is on SKIP_SELF_FIX, which advances the ledger (`--dry-run`
        decides without writing).
  get --kind <bucket|ledger>
        Prints {"number": N|null, "body": "...", "strays": [...]}.
  upsert --kind <bucket> --label L --title T --body-file F
        Creates or edits the one managed issue for that kind; prints its URL.
  ledger-write
        Records the default-branch sha, today's date and the rubric sha.

Significance = added + deleted lines over the commits since the ledger sha
that do not reference one of this repo's own audit issues, counting only
source paths (docs, markdown, tests and lockfiles weigh nothing). Every
unknown fails open to AUDIT: a missing or unreadable ledger, an unreachable
baseline, an unexplained commit with no diff data.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):  # pragma: no cover
    pass

NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

BUCKETS = ("bug", "stale", "slop", "documentation")
KINDS = ("ledger",) + BUCKETS
LEDGER_TITLE = "codebase-audit ledger"
LEDGER_LABEL = "audit-meta"
DEFAULT_THRESHOLD = 1000
# First existing file wins; its sha256 is the `rubric-sha` so a rubric edit
# with no source change still triggers an audit. CLAUDE.md first: the private
# tool hashes exactly that file, so a repo audited by both agrees on the hash.
RUBRIC_CANDIDATES = ("CLAUDE.md", "AGENTS.md", "copilot-instructions.md",
                     ".github/copilot-instructions.md")
_LOCKFILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
              "Pipfile.lock", "Cargo.lock", "uv.lock", "composer.lock", "Gemfile.lock"}

_MARKER_RE = re.compile(r"^[ \t]*<!--[ \t]*audit-managed:[ \t]*kind=([\w-]+)[ \t]*-->[ \t]*$", re.MULTILINE)
_LEDGER_MARKER = "<!-- audit-ledger -->"
_LEDGER_MARKER_OPEN = "<!-- audit-ledger"
_LEDGER_SHA_RE = re.compile(r"^last-audited-sha:[ \t]*(\S+)[ \t]*$", re.MULTILINE)
_LEDGER_AT_RE = re.compile(r"^last-audited-at:[ \t]*(\S+)[ \t]*$", re.MULTILINE)
_LEDGER_RUBRIC_RE = re.compile(r"^rubric-sha:[ \t]*(.*?)[ \t]*$", re.MULTILINE)
_ISSUE_REF_RE = re.compile(r"(?<![\w/])#(\d+)\b")
_BRANCH_REF_RE = re.compile(r"\b[a-z]+/(\d+)-[\w-]+")


# ---- pure helpers (unit-tested without git/gh/glab) ------------------------

def marker_for(kind: str) -> str:
    return f"<!-- audit-managed: kind={kind} -->"


def has_marker(body: str, kind: str) -> bool:
    """True only when the marker is the first line — a body that merely quotes
    the marker in prose (e.g. an issue documenting this format) is not managed."""
    m = _MARKER_RE.match((body or "").lstrip())
    return bool(m) and m.group(1) == kind


def ensure_marker(body: str, kind: str) -> str:
    stripped = _MARKER_RE.sub("", body or "").lstrip("\n")
    return f"{marker_for(kind)}\n\n{stripped}" if stripped else f"{marker_for(kind)}\n"


def title_matches(title: str, kind: str) -> bool:
    t = (title or "").strip()
    if kind == "ledger":
        return t == LEDGER_TITLE
    return re.match(r"^audit:\s*" + re.escape(kind) + r"\s+findings\b", t) is not None


def plan(issues: list[dict], kind: str) -> tuple[int | None, list[int]]:
    """(issue to keep, strays) among `issues` for `kind` — lowest number wins."""
    found = sorted(i["number"] for i in issues
                   if has_marker(i.get("body", ""), kind) or title_matches(i.get("title", ""), kind))
    return (found[0], found[1:]) if found else (None, [])


def managed_numbers(issues: list[dict]) -> set[int]:
    """Every issue (any state) that is one of this repo's audit bucket issues."""
    return {i["number"] for i in issues
            if any(has_marker(i.get("body", ""), k) or title_matches(i.get("title", ""), k) for k in BUCKETS)}


def rubric_sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def rubric_path(repo_path: str) -> Path | None:
    for name in RUBRIC_CANDIDATES:
        p = Path(repo_path) / name
        if p.is_file():
            return p
    return None


def rubric_sha_of_path(repo_path: str) -> str:
    p = rubric_path(repo_path)
    return rubric_sha(p.read_bytes()) if p else ""


def parse_ledger(body: str) -> dict:
    """{sha, at, rubric} from the ledger block; None for a missing field. An
    empty rubric is a legitimate value (repo has no instructions file)."""
    body = (body or "").replace("\r\n", "\n").replace("\r", "\n")
    idx = body.find(_LEDGER_MARKER_OPEN)
    if idx == -1:
        return {"sha": None, "at": None, "rubric": None}
    block = body[idx:]
    sha_m, at_m, rub_m = _LEDGER_SHA_RE.search(block), _LEDGER_AT_RE.search(block), _LEDGER_RUBRIC_RE.search(block)
    return {"sha": sha_m.group(1) if sha_m else None,
            "at": at_m.group(1) if at_m else None,
            "rubric": rub_m.group(1) if rub_m else None}


def render_ledger_body(sha: str, at: str, rubric: str) -> str:
    """The one place a ledger body is composed — same block the private tool writes."""
    return ("Machine-readable ledger for `/codebase-audit`. Do not edit by hand — "
            "the skill upserts this on each whole-repo run. Labelled `audit-meta` "
            "so it never surfaces as actionable work.\n\n"
            f"{_LEDGER_MARKER}\nlast-audited-sha: {sha}\nlast-audited-at: {at}\nrubric-sha: {rubric}\n")


def is_source_path(path: str) -> bool:
    """Paths that count toward significance. Docs, markdown, tests and
    lockfiles weigh nothing — a doc sweep must never buy a re-audit."""
    parts = [p for p in path.replace("\\", "/").split("/") if p]
    if not parts:
        return False
    name = parts[-1]
    if any(p in ("docs", "doc", "tests", "test") for p in parts[:-1]):
        return False
    if name.lower().endswith((".md", ".rst", ".txt", ".lock")) or name in _LOCKFILES:
        return False
    if name.startswith("test_") or re.search(r"_test\.\w+$", name) or name.endswith(".test.js"):
        return False
    return True


def parse_numstat(text: str) -> int:
    """Added + deleted over `git diff --numstat` output, source paths only;
    binary rows (`-`) contribute nothing rather than crashing."""
    total = 0
    for line in (text or "").splitlines():
        cols = line.split("\t", 2)
        if len(cols) != 3 or not is_source_path(cols[2]):
            continue
        try:
            total += int(cols[0]) + int(cols[1])
        except ValueError:
            continue
    return total


def references_managed(message: str, managed: set[int]) -> bool:
    """A commit is a self-fix when its message cites one of this repo's audit
    issues — `#N` (Closes #N, squash subject) or a `<type>/N-slug` branch name."""
    refs = {int(n) for n in _ISSUE_REF_RE.findall(message or "")}
    refs |= {int(n) for n in _BRANCH_REF_RE.findall(message or "")}
    return bool(refs & managed)


def decide(commit_count: int | None, stored_rubric: str | None, current_rubric: str,
           self_fix: bool = False, significance: int | None = None,
           threshold: int = DEFAULT_THRESHOLD) -> str:
    """The one place the skip/audit call is made. Fails open to AUDIT on any
    unknown; zero commits lets the rubric decide; self-fix-only churn skips
    and advances; organic change below the threshold accumulates quietly."""
    if commit_count is None or stored_rubric is None:
        return "AUDIT"
    if commit_count == 0:
        return "SKIP" if stored_rubric == current_rubric else "AUDIT"
    if self_fix:
        return "SKIP_SELF_FIX"
    if significance is not None and significance < threshold:
        return "SKIP_BELOW_THRESHOLD"
    return "AUDIT"


def parse_owner_repo(remote_url: str) -> str:
    """'owner/repo' (GitLab subgroups keep their slashes) or '' if unparseable."""
    u = re.sub(r"\.git$", "", (remote_url or "").strip())
    if not u:
        return ""
    if "://" in u:
        m = re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://[^/]+/(.+)$", u)
        path = m.group(1) if m else ""
    else:
        path = u.partition(":")[2]
    parts = [p for p in path.strip("/").split("/") if p]
    return "/".join(parts) if len(parts) >= 2 else ""


def detect_host(remote_url: str) -> str:
    return "github" if "github.com" in (remote_url or "") else "gitlab"


# ---- git plumbing -----------------------------------------------------------

def _run(cmd: list[str], cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=120, creationflags=NO_WINDOW)


def git(repo_path: str, *args: str) -> str | None:
    """stdout of a git command, or None on any failure."""
    try:
        r = _run(["git", *args], cwd=repo_path)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def default_branch_ref(repo_path: str) -> str:
    ref = git(repo_path, "symbolic-ref", "-q", "refs/remotes/origin/HEAD")
    if ref:
        return ref
    for cand in ("origin/main", "origin/master", "main", "master"):
        if git(repo_path, "rev-parse", "--verify", "--quiet", f"{cand}^{{commit}}") is not None:
            return cand
    return "HEAD"


def default_branch_sha(repo_path: str) -> str | None:
    """The only sha safe to record: a default-branch commit survives a
    squash-merge + branch delete, a feature-branch tip does not."""
    return git(repo_path, "rev-parse", "--verify", "--quiet", f"{default_branch_ref(repo_path)}^{{commit}}")


def sha_reachable(repo_path: str, sha: str) -> bool:
    return bool(sha) and git(repo_path, "merge-base", "--is-ancestor", sha, default_branch_ref(repo_path)) is not None


def commits_since(repo_path: str, sha: str) -> list[str] | None:
    """Mainline commits from `sha` to the default branch — `--first-parent` so a
    regular merge counts once (its merge commit), like a squash does."""
    out = git(repo_path, "rev-list", "--first-parent", f"{sha}..{default_branch_ref(repo_path)}")
    return out.split() if out is not None else None


def commit_numstat(repo_path: str, sha: str) -> str | None:
    out = git(repo_path, "diff", "--numstat", f"{sha}^", sha)
    if out is None:  # root commit: no parent to diff against
        out = git(repo_path, "show", "--numstat", "--format=", sha)
    return out


def significance_since(repo_path: str, shas: list[str], managed: set[int]) -> tuple[list[str], int | None]:
    """(organic commits, their source-LOC total). None when a commit's diff
    could not be read — an unknown must never under-count into a skip."""
    organic, total = [], 0
    for sha in shas:
        msg = git(repo_path, "log", "-1", "--format=%B", sha) or ""
        if references_managed(msg, managed):
            continue
        organic.append(sha)
        stat = commit_numstat(repo_path, sha)
        if stat is None:
            return organic, None
        total += parse_numstat(stat)
    return organic, total


# ---- gh / glab plumbing -----------------------------------------------------

def resolve_repo(repo_path: str) -> tuple[str, str]:
    url = git(repo_path, "remote", "get-url", "origin") or ""
    repo = parse_owner_repo(url)
    if not repo:
        raise SystemExit(f"cannot resolve owner/repo from origin of {repo_path}")
    return detect_host(url), repo


def _cli(host: str, args: list[str]) -> str:
    cli = "gh" if host == "github" else "glab"
    try:
        r = _run([cli, *args])
    except (OSError, subprocess.SubprocessError) as exc:
        raise SystemExit(f"{cli} {' '.join(args[:3])} failed: {exc}")
    if r.returncode != 0:
        raise SystemExit(f"{cli} {' '.join(args[:3])} exit {r.returncode}: {r.stderr.strip()[:200]}")
    return r.stdout.strip()


def list_issues(host: str, repo: str, label: str) -> list[dict]:
    """Issues carrying `label`, any state, normalised to {number, title, body,
    state}. Always label-filtered: an unfiltered list is capped by the CLI and
    silently misses the ledger on a repo with hundreds of issues."""
    if host == "github":
        out = _cli(host, ["issue", "list", "--repo", repo, "--state", "all", "--label", label,
                          "--limit", "300", "--json", "number,title,body,state"])
        return [{**i, "state": (i.get("state") or "").lower()} for i in (json.loads(out) if out else [])]
    # glab: best-effort per documented CLI shape, not live-tested here.
    out = _cli(host, ["issue", "list", "--repo", repo, "--all", "--label", label, "--per-page", "100",
                      "--output", "json"])
    return [{"number": i.get("iid"), "title": i.get("title", ""), "body": i.get("description") or "",
             "state": "open" if i.get("state") == "opened" else "closed"}
            for i in (json.loads(out) if out else [])]


def open_issues(host: str, repo: str, label: str) -> list[dict]:
    return [i for i in list_issues(host, repo, label) if i["state"] == "open"]


def issue_url(host: str, repo: str, number: int) -> str:
    if host == "github":
        return _cli(host, ["issue", "view", str(number), "--repo", repo, "--json", "url", "-q", ".url"])
    out = _cli(host, ["issue", "view", str(number), "--repo", repo, "--output", "json"])
    return (json.loads(out) if out else {}).get("web_url", "")


def ensure_label(host: str, repo: str, label: str) -> None:
    args = (["label", "create", label, "--repo", repo] if host == "github"
            else ["label", "create", "--repo", repo, "-n", label])
    try:
        _run(["gh" if host == "github" else "glab", *args])  # duplicate-create fails harmlessly
    except (OSError, subprocess.SubprocessError):
        pass


def _write_tmp(body: str) -> str:
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8", newline="")
    f.write(body)
    f.close()
    return f.name


def upsert_issue(host: str, repo: str, kind: str, title: str, body: str, label: str) -> str:
    """Create or edit the single managed issue for `kind`; never a second one."""
    keep, strays = plan(open_issues(host, repo, label), kind)
    if strays:
        print(f"warning: extra {kind} issues left untouched: {strays}", file=sys.stderr)
    tmp = _write_tmp(ensure_marker(body, kind))
    try:
        ensure_label(host, repo, label)
        if keep is None:
            if host == "github":
                return _cli(host, ["issue", "create", "--repo", repo, "--title", title, "--body-file", tmp,
                                   "--label", label, "--assignee", "@me"])
            out = _cli(host, ["issue", "create", "--repo", repo, "--title", title, "--description-file", tmp,
                              "--label", label, "--assignee", "@me", "--yes"])
            return out.splitlines()[-1] if out else ""
        if host == "github":
            _cli(host, ["issue", "edit", str(keep), "--repo", repo, "--title", title, "--body-file", tmp,
                        "--add-label", label])
        else:
            _cli(host, ["issue", "update", str(keep), "--repo", repo, "--title", title,
                        "--description-file", tmp, "--label", label])
        return issue_url(host, repo, keep)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def comment_issue(host: str, repo: str, number: int, body: str) -> None:
    tmp = _write_tmp(body)
    try:
        if host == "github":
            _cli(host, ["issue", "comment", str(number), "--repo", repo, "--body-file", tmp])
        else:
            _cli(host, ["issue", "note", str(number), "--repo", repo, "--message-file", tmp])
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


# ---- subcommands ------------------------------------------------------------

def write_ledger(host: str, repo: str, repo_path: str) -> str:
    sha = default_branch_sha(repo_path)
    if sha is None or not sha_reachable(repo_path, sha):
        raise SystemExit(f"no verifiable default-branch commit in {repo_path} — refusing to record a ledger sha")
    body = render_ledger_body(sha, datetime.date.today().isoformat(), rubric_sha_of_path(repo_path))
    return upsert_issue(host, repo, "ledger", LEDGER_TITLE, body, LEDGER_LABEL)


def cmd_gate(repo_path: str, threshold: int, fetch: bool, dry_run: bool = False) -> dict:
    host, repo = resolve_repo(repo_path)
    ledgers = open_issues(host, repo, LEDGER_LABEL)
    keep, _ = plan(ledgers, "ledger")
    if keep is None:
        return {"decision": "AUDIT", "reason": "no-ledger"}
    ledger = parse_ledger(next(i["body"] for i in ledgers if i["number"] == keep))
    if ledger["sha"] is None or ledger["rubric"] is None:
        return {"decision": "AUDIT", "reason": "unparseable-ledger", "ledger_issue": keep}
    if fetch:
        git(repo_path, "fetch", "--quiet", "origin")  # best effort; local refs still work offline
    if not sha_reachable(repo_path, ledger["sha"]):
        return {"decision": "AUDIT", "reason": "unresolvable-baseline", "ledger_issue": keep,
                "last_sha": ledger["sha"]}
    shas = commits_since(repo_path, ledger["sha"])
    current_rubric = rubric_sha_of_path(repo_path)
    result = {"ledger_issue": keep, "last_sha": ledger["sha"], "last_at": ledger["at"],
              "commits": None if shas is None else len(shas), "significance": None, "threshold": threshold}
    if not shas:
        decision = decide(None if shas is None else 0, ledger["rubric"], current_rubric)
    else:
        managed = set().union(*(managed_numbers(list_issues(host, repo, b)) for b in BUCKETS))
        organic, significance = significance_since(repo_path, shas, managed)
        result["organic_commits"] = len(organic)
        result["significance"] = significance
        decision = decide(len(shas), ledger["rubric"], current_rubric,
                          self_fix=not organic, significance=significance, threshold=threshold)
    result["decision"], result["reason"] = decision, decision.lower().replace("_", "-")
    if decision == "SKIP_SELF_FIX" and not dry_run:
        url = write_ledger(host, repo, repo_path)
        today = datetime.date.today().isoformat()
        comment_issue(host, repo, keep, f"<!-- audit-self-fix -->\nSelf-fix sweep — {today}: the "
                      f"{len(shas)} commit(s) since {ledger['sha'][:7]} only reference this repo's own "
                      "audit issues; ledger advanced without a re-read.")
        result["ledger_url"] = url
    return result


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo-path", default=".")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gate")
    g.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    g.add_argument("--no-fetch", action="store_true")
    g.add_argument("--dry-run", action="store_true", help="never advance the ledger, only decide")
    gt = sub.add_parser("get")
    gt.add_argument("--kind", required=True, choices=KINDS)
    u = sub.add_parser("upsert")
    u.add_argument("--kind", required=True, choices=BUCKETS)
    u.add_argument("--label", required=True)
    u.add_argument("--title", required=True)
    u.add_argument("--body-file", required=True)
    sub.add_parser("ledger-write")
    args = ap.parse_args(argv)

    repo_path = str(Path(args.repo_path).resolve())
    if args.cmd == "gate":
        print(json.dumps(cmd_gate(repo_path, args.threshold, not args.no_fetch, args.dry_run)))
        return
    host, repo = resolve_repo(repo_path)
    if args.cmd == "get":
        candidates = open_issues(host, repo, LEDGER_LABEL if args.kind == "ledger" else args.kind)
        keep, strays = plan(candidates, args.kind)
        body = next((i["body"] for i in candidates if i["number"] == keep), "") if keep else ""
        print(json.dumps({"number": keep, "body": body.replace("\r\n", "\n"), "strays": strays}))
    elif args.cmd == "upsert":
        body = Path(args.body_file).read_text(encoding="utf-8")
        print(upsert_issue(host, repo, args.kind, args.title, body, args.label))
    elif args.cmd == "ledger-write":
        print(write_ledger(host, repo, repo_path))


if __name__ == "__main__":
    main()
