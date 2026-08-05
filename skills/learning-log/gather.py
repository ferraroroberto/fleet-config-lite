"""Gather + bucket + stat the sibling-repo work stream for /learning-log (lite).

Host-agnostic port of fleet-config's `.claude/skills/learning-log/gather.py`,
scoped down for fleet-config-lite: no dependency on any fleet-config-only
helper (`audit_issue.py`, `no_window.py`, `claude_progress.py`,
`notify_complete.py` don't exist here), no scheduler, self-contained.

Detects whether the *current* repo's `origin` remote is GitHub or GitLab
(`git remote get-url origin`) and drives the matching CLI (`gh` or `glab`)
throughout — the sibling repos gathered are whichever other repos share the
same owner/group on that same host. This repo itself is GitHub-hosted and
`gh` is what's actually installed on the dev machine this was built on, so
the GitHub path is exercised live. The GitLab path is written to `glab`'s
documented CLI shape but is **not** live-tested here (`glab` isn't installed
on this machine) — the same caveat already applies to this repo's other
`glab`-based skills (issue-add/issue-start/issue-finish).

It does NOT narrate — that's the calling skill's job (SKILL.md), which reads
the bucket files and dispatches an insight sub-agent per bucket. This script
only computes deterministic facts: counts, LOC, bucket membership, ledger
state. Stdlib + `gh`/`glab` only.

Subcommands:

  probe                     Print HOST / OWNER / REPO / REPO_FULL detected
                            from the current repo's origin remote.

  gather   [--since YYYY-MM-DD] [--out-dir DIR]
                            Lists sibling repos on the same host/owner, reads
                            merged PRs/MRs + closed issues per repo since
                            `--since` (else the ledger's last-run-at, else
                            trailing 7 days), buckets + stats them, writes
                            <out-dir>/stats.md, prior-horizon.md, and one
                            bucket-<slug>.md per non-empty bucket. Prints a
                            parseable manifest the calling skill dispatches
                            sub-agents from.

  assemble-ledger --horizon-file F --discoveries-file F --out F
                            Reads the prior ledger issue's body, preserves
                            its durable archive, prepends this run's dated
                            discoveries, swaps in the new horizon, and stamps
                            last-run-at — emits the ledger body for upsert.

  upsert-ledger --body-file F
                            Finds the open ledger issue (by the fixed label,
                            created if missing) and edits it, or creates it
                            if none exists. Prints LEDGER_URL / LEDGER_NUMBER.

  comment --issue N --body-file F
                            Posts the weekly digest as a comment on the
                            ledger issue. Prints COMMENT_URL.

Window anchors to the ledger's last-run-at so a missed run widens the next.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
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

LEDGER_TITLE = "Learning log"
LEDGER_LABEL = "learning-log"
STATE_MARKER = "<!-- learning-log-state -->"
ARCHIVE_HEADER = "## Decision / discovery archive"
HORIZON_HEADER = "## Horizon -> next week"

# Canonical work-type buckets, in display order. PR/MR titles are conventional-
# commit prefixed; issues carry type labels. Both map onto the same set so a
# bucket shows PRs/MRs and issues together.
BUCKETS = [
    "Features & enhancements",
    "Bug fixes",
    "Chores & maintenance",
    "Documentation",
    "Refactors",
    "Tooling, CI & perf",
    "Other",
]
_PREFIX_BUCKET = {
    "feat": "Features & enhancements", "feature": "Features & enhancements",
    "fix": "Bug fixes", "bug": "Bug fixes", "hotfix": "Bug fixes",
    "chore": "Chores & maintenance", "build": "Chores & maintenance", "deps": "Chores & maintenance",
    "docs": "Documentation", "doc": "Documentation",
    "refactor": "Refactors",
    "perf": "Tooling, CI & perf", "test": "Tooling, CI & perf",
    "ci": "Tooling, CI & perf", "style": "Tooling, CI & perf",
}
_LABEL_BUCKET = {
    "bug": "Bug fixes", "enhancement": "Features & enhancements",
    "chore": "Chores & maintenance", "documentation": "Documentation",
    "refactor": "Refactors", "maintainability": "Refactors", "duplicate": "Chores & maintenance",
}


# ---- pure helpers (unit-tested without gh/glab) ----------------------------

def parse_owner_repo(remote_url: str) -> tuple[str, str]:
    """(owner_or_group, repo_name) from an https:// or git@ remote URL.

    Supports GitLab subgroups (owner may contain '/'), e.g.
    'https://gitlab.example.com/group/subgroup/project.git' ->
    ('group/subgroup', 'project').
    """
    u = (remote_url or "").strip()
    u = re.sub(r"\.git$", "", u)
    if not u:
        return "", ""
    if u.startswith("git@") or (":" in u and "://" not in u):
        _, _, rest = u.partition("@") if "@" in u else ("", "", u)
        host_and_path = rest or u
        _, _, path = host_and_path.partition(":")
    else:
        m = re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://[^/]+/(.+)$", u)
        path = m.group(1) if m else ""
    parts = [p for p in path.strip("/").split("/") if p]
    if len(parts) < 2:
        return "", ""
    return "/".join(parts[:-1]), parts[-1]


def detect_host(remote_url: str) -> str:
    """'github' if the remote is github.com, else 'gitlab' (gitlab.com or self-hosted)."""
    return "github" if "github.com" in (remote_url or "") else "gitlab"


def parse_last_run(body: str) -> str | None:
    m = re.search(r"last-run-at:\s*(\d{4}-\d{2}-\d{2})", body or "")
    return m.group(1) if m else None


def resolve_since(arg: str | None, prior_body: str, today: _dt.date) -> tuple[str, str]:
    """(since, source) -- explicit arg -> ledger last-run-at -> trailing 7 days."""
    if arg:
        return arg, "arg"
    last = parse_last_run(prior_body)
    if last:
        return last, "ledger"
    return (today - _dt.timedelta(days=7)).isoformat(), "default"


def slice_section(text: str, header: str) -> str:
    idx = (text or "").find(header)
    if idx == -1:
        return ""
    rest = text[idx + len(header):]
    end = rest.find("\n## ")
    return (rest if end == -1 else rest[:end]).strip()


def _bullet_lines(section: str) -> list[str]:
    return [ln.strip() for ln in (section or "").splitlines() if ln.strip().startswith(("-", "*"))]


def dated_discovery_bullets(discoveries: str, today: str, cap: int = 12) -> list[str]:
    out: list[str] = []
    for ln in _bullet_lines(discoveries)[:cap]:
        content = ln.lstrip("-*").strip()
        if content:
            out.append(f"- {today}: {content}")
    return out


def extract_archive_bullets(prior_body: str) -> list[str]:
    return _bullet_lines(slice_section(prior_body, ARCHIVE_HEADER))


def build_ledger_body(prior_body: str, today: str, horizon: str, discoveries: str) -> str:
    horizon_md = "\n".join(_bullet_lines(horizon)) or "- [ ] (none captured this run)"
    archive = dated_discovery_bullets(discoveries, today) + extract_archive_bullets(prior_body)
    archive_md = "\n".join(archive) if archive else "- (nothing archived yet)"
    return (
        f"{STATE_MARKER}\n"
        f"last-run-at: {today}\n\n"
        f"# {LEDGER_TITLE}\n\n"
        "The learning journal for this repo's sibling-repo family -- what shipped, "
        "what we learned, and what's next -- from merged PRs/MRs + closed issues, "
        "mined per work-type bucket by `/learning-log`. The week-by-week narrative + "
        "productivity tables live in this issue's comments; this body is the durable "
        "archive + the live horizon.\n\n"
        f"## Horizon -> next week (set {today})\n{horizon_md}\n\n"
        f"{ARCHIVE_HEADER}\n{archive_md}\n"
    )


def _type_prefix(title: str) -> str:
    m = re.match(r"\s*([a-z]+)(?:\([^)]*\))?!?:", title or "", re.I)
    return m.group(1).lower() if m else ""


def pr_bucket(title: str) -> str:
    return _PREFIX_BUCKET.get(_type_prefix(title), "Other")


def issue_bucket(labels: list[str]) -> str:
    for lb in labels:
        if lb in _LABEL_BUCKET:
            return _LABEL_BUCKET[lb]
    return "Other"


def _slug(bucket: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", bucket.lower()).strip("-")


def compute_stats(prs: list[dict], issues: list[dict]) -> dict:
    """Per-repo and per-bucket counts + LOC, plus grand totals. Pure."""
    repos: dict[str, dict] = {}
    buckets: dict[str, dict] = {b: {"prs": 0, "issues": 0, "add": 0, "del": 0} for b in BUCKETS}

    def repo_row(name: str) -> dict:
        return repos.setdefault(name, {"prs": 0, "issues": 0, "add": 0, "del": 0})

    for p in prs:
        r = repo_row(p["repo"]); b = buckets[p["bucket"]]
        add, dele = int(p.get("additions") or 0), int(p.get("deletions") or 0)
        r["prs"] += 1; r["add"] += add; r["del"] += dele
        b["prs"] += 1; b["add"] += add; b["del"] += dele
    for i in issues:
        repo_row(i["repo"])["issues"] += 1
        buckets[i["bucket"]]["issues"] += 1

    total = {"prs": len(prs), "issues": len(issues),
             "add": sum(int(p.get("additions") or 0) for p in prs),
             "del": sum(int(p.get("deletions") or 0) for p in prs)}
    return {"repos": repos, "buckets": buckets, "total": total}


def _fmt_loc(n: int) -> str:
    return f"{n/1000:.1f}k" if n >= 1000 else str(n)


def render_stats(stats: dict, since: str, today: str) -> str:
    total = stats["total"]
    lines = [
        f"## Productivity -- {since} -> {today}",
        "",
        f"**Grand total:** {total['prs']} merged PRs/MRs, {total['issues']} closed issues, "
        f"+{_fmt_loc(total['add'])} / -{_fmt_loc(total['del'])} LOC across "
        f"{sum(1 for r in stats['repos'].values() if r['prs'] or r['issues'])} active repos.",
        "",
        "### By repo (most active first)",
        "",
        "| Repo | PRs/MRs | Issues | +LOC | -LOC |",
        "|---|--:|--:|--:|--:|",
        f"| **TOTAL** | **{total['prs']}** | **{total['issues']}** | **+{_fmt_loc(total['add'])}** | **-{_fmt_loc(total['del'])}** |",
    ]
    for name, r in sorted(stats["repos"].items(), key=lambda kv: (-kv[1]["prs"], -kv[1]["issues"], kv[0])):
        if not (r["prs"] or r["issues"]):
            continue
        lines.append(f"| {name} | {r['prs']} | {r['issues']} | +{_fmt_loc(r['add'])} | -{_fmt_loc(r['del'])} |")

    lines += ["", "### By work type", "", "| Bucket | PRs/MRs | Issues | +LOC | -LOC |", "|---|--:|--:|--:|--:|"]
    for b in BUCKETS:
        d = stats["buckets"][b]
        if not (d["prs"] or d["issues"]):
            continue
        lines.append(f"| {b} | {d['prs']} | {d['issues']} | +{_fmt_loc(d['add'])} | -{_fmt_loc(d['del'])} |")
    return "\n".join(lines) + "\n"


def write_bucket_files(out_dir: Path, prs: list[dict], issues: list[dict]) -> list[tuple[str, str, int, int, Path]]:
    """One file per non-empty bucket; returns (bucket, slug, n_prs, n_issues, path)."""
    manifest = []
    for bucket in BUCKETS:
        bp = [p for p in prs if p["bucket"] == bucket]
        bi = [i for i in issues if i["bucket"] == bucket]
        if not (bp or bi):
            continue
        slug = _slug(bucket)
        path = out_dir / f"bucket-{slug}.md"
        lines = [f"# Bucket: {bucket}", f"_{len(bp)} merged PRs/MRs, {len(bi)} closed issues_", "", "## Merged PRs/MRs"]
        for p in sorted(bp, key=lambda x: -((x.get("additions") or 0) + (x.get("deletions") or 0))):
            lines.append(f"- [{p['repo']}#{p['number']}] {p['title']} (+{p.get('additions') or 0}/-{p.get('deletions') or 0})")
        lines += ["", "## Closed issues"]
        for i in bi:
            tag = f" [{','.join(i['labels'])}]" if i["labels"] else ""
            lines.append(f"- [{i['repo']}#{i['number']}] {i['title']}{tag}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        manifest.append((bucket, slug, len(bp), len(bi), path))
    return manifest


# ---- git / gh / glab plumbing ----------------------------------------------

def _run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, creationflags=NO_WINDOW)


def _cli_json(cli: str, args: list[str]) -> list | dict:
    try:
        proc = _run([cli, *args])
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"{cli} {' '.join(args[:3])}... failed: {exc}", file=sys.stderr)
        return []
    if proc.returncode != 0:
        print(f"{cli} {' '.join(args[:3])}... exit {proc.returncode}: {proc.stderr.strip()[:160]}", file=sys.stderr)
        return []
    try:
        return json.loads(proc.stdout or "[]")
    except ValueError:
        return []


def git_remote_url(remote: str = "origin") -> str:
    try:
        proc = _run(["git", "remote", "get-url", remote], timeout=15)
    except (OSError, subprocess.SubprocessError):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def resolve_repo_context() -> tuple[str, str, str, str]:
    """(host, owner, repo, repo_full) for the current checkout's origin remote."""
    url = git_remote_url()
    host = detect_host(url)
    owner, repo = parse_owner_repo(url)
    repo_full = f"{owner}/{repo}" if owner and repo else ""
    return host, owner, repo, repo_full


def list_sibling_repos(host: str, owner: str) -> list[str]:
    """Public repos under the same owner/group -- never enumerates private
    siblings, since this run's output may land in a ledger issue that is
    itself public even when some siblings are not (privacy default carried
    over from fleet-config's own /learning-log)."""
    if host == "github":
        data = _cli_json("gh", ["repo", "list", owner, "--no-archived", "--source",
                                "--visibility", "public", "--limit", "200", "--json", "name"])
        return [r["name"] for r in data] if isinstance(data, list) else []
    # glab: best-effort per documented CLI shape, not live-tested (see module docstring).
    data = _cli_json("glab", ["repo", "list", "--group", owner, "--visibility", "public",
                              "--per-page", "200", "--output", "json"])
    if isinstance(data, list):
        return [r.get("path") or r.get("name") for r in data if r.get("path") or r.get("name")]
    return []


def gather_repo(host: str, owner: str, repo: str, since: str) -> tuple[list[dict], list[dict]]:
    full = f"{owner}/{repo}"
    if host == "github":
        prs_raw = _cli_json("gh", ["pr", "list", "--repo", full, "--state", "merged", "--limit", "400",
                                   "--json", "number,title,additions,deletions,labels,mergedAt,url"])
        issues_raw = _cli_json("gh", ["issue", "list", "--repo", full, "--state", "closed", "--limit", "400",
                                      "--json", "number,title,labels,closedAt,url"])
        merged_key, closed_key = "mergedAt", "closedAt"
    else:
        # glab: best-effort per documented CLI shape, not live-tested (see module docstring).
        # GitLab's MR/issue list JSON doesn't expose per-item diff stats the way
        # GitHub's does, so additions/deletions stay 0 for the GitLab path --
        # a known fidelity gap, not a bug.
        prs_raw = _cli_json("glab", ["mr", "list", "--repo", full, "--state", "merged",
                                     "--per-page", "100", "--output", "json"])
        issues_raw = _cli_json("glab", ["issue", "list", "--repo", full, "--state", "closed",
                                        "--per-page", "100", "--output", "json"])
        merged_key, closed_key = "merged_at", "closed_at"

    prs = []
    for p in (prs_raw if isinstance(prs_raw, list) else []):
        if (p.get(merged_key) or "")[:10] < since:
            continue
        prs.append({"repo": repo, "number": p.get("number") or p.get("iid"), "title": p.get("title", ""),
                    "additions": p.get("additions"), "deletions": p.get("deletions"),
                    "url": p.get("url") or p.get("web_url"), "bucket": pr_bucket(p.get("title", ""))})
    issues = []
    for i in (issues_raw if isinstance(issues_raw, list) else []):
        if (i.get(closed_key) or "")[:10] < since:
            continue
        raw_labels = i.get("labels") or []
        labels = [l.get("name", "") for l in raw_labels] if raw_labels and isinstance(raw_labels[0], dict) else list(raw_labels)
        issues.append({"repo": repo, "number": i.get("number") or i.get("iid"), "title": i.get("title", ""),
                       "labels": labels, "url": i.get("url") or i.get("web_url"), "bucket": issue_bucket(labels)})
    return prs, issues


def ensure_ledger_label(host: str, repo_full: str) -> None:
    if host == "github":
        existing = _cli_json("gh", ["label", "list", "--repo", repo_full, "--json", "name", "--limit", "200"])
        names = {l.get("name") for l in existing} if isinstance(existing, list) else set()
        if LEDGER_LABEL not in names:
            _run(["gh", "label", "create", LEDGER_LABEL, "--repo", repo_full,
                 "--color", "0e8a16", "--description", "learning-log ledger (machine-managed)"])
    else:
        # glab: best-effort per documented CLI shape, not live-tested.
        _run(["glab", "label", "create", LEDGER_LABEL, "--repo", repo_full,
             "--color", "#0e8a16", "--description", "learning-log ledger (machine-managed)"])


def read_ledger(host: str, repo_full: str) -> tuple[int | None, str, str | None]:
    """(issue_number, body, url) of the open ledger issue, or (None, "", None)."""
    if host == "github":
        data = _cli_json("gh", ["issue", "list", "--repo", repo_full, "--label", LEDGER_LABEL,
                                "--state", "open", "--json", "number,body,url", "--limit", "5"])
    else:
        data = _cli_json("glab", ["issue", "list", "--repo", repo_full, "--label", LEDGER_LABEL,
                                  "--state", "opened", "--per-page", "5", "--output", "json"])
    items = data if isinstance(data, list) else []
    if not items:
        return None, "", None
    it = items[0]
    return (it.get("number") or it.get("iid"), it.get("body") or it.get("description") or "",
            it.get("url") or it.get("web_url"))


def upsert_ledger(host: str, repo_full: str, body: str) -> tuple[int | None, str | None]:
    ensure_ledger_label(host, repo_full)
    number, _prior_body, _url = read_ledger(host, repo_full)
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(body)
        body_file = f.name
    try:
        if number:
            if host == "github":
                _run(["gh", "issue", "edit", str(number), "--repo", repo_full, "--body-file", body_file])
                proc = _cli_json("gh", ["issue", "view", str(number), "--repo", repo_full, "--json", "url"])
                url = proc.get("url") if isinstance(proc, dict) else None
            else:
                _run(["glab", "issue", "update", str(number), "--repo", repo_full, "--description-file", body_file])
                proc = _cli_json("glab", ["issue", "view", str(number), "--repo", repo_full, "--output", "json"])
                url = proc.get("web_url") if isinstance(proc, dict) else None
            return number, url
        if host == "github":
            proc = _run(["gh", "issue", "create", "--repo", repo_full, "--title", LEDGER_TITLE,
                        "--body-file", body_file, "--label", LEDGER_LABEL, "--assignee", "@me"])
            url = proc.stdout.strip() if proc.returncode == 0 else None
        else:
            proc = _run(["glab", "issue", "create", "--repo", repo_full, "--title", LEDGER_TITLE,
                        "--description-file", body_file, "--label", LEDGER_LABEL, "--assignee", "@me"])
            url = proc.stdout.strip() if proc.returncode == 0 else None
        new_number = None
        if url:
            m = re.search(r"/(\d+)$", url.splitlines()[-1] if url else "")
            new_number = int(m.group(1)) if m else None
        return new_number, (url.splitlines()[-1] if url else None)
    finally:
        Path(body_file).unlink(missing_ok=True)


def post_comment(host: str, repo_full: str, issue_number: int, body_file: str) -> str | None:
    if host == "github":
        proc = _run(["gh", "issue", "comment", str(issue_number), "--repo", repo_full, "--body-file", body_file])
    else:
        proc = _run(["glab", "issue", "note", str(issue_number), "--repo", repo_full, "--message-file", body_file])
    return proc.stdout.strip() if proc.returncode == 0 else None


# ---- subcommands ------------------------------------------------------------

def cmd_probe(_args) -> int:
    host, owner, repo, repo_full = resolve_repo_context()
    print(f"HOST={host}")
    print(f"OWNER={owner}")
    print(f"REPO={repo}")
    print(f"REPO_FULL={repo_full}")
    return 0 if repo_full else 1


def cmd_gather(args) -> int:
    today = _dt.date.today().isoformat()
    host, owner, _repo, repo_full = resolve_repo_context()
    if not repo_full:
        print("Could not resolve owner/repo from `git remote get-url origin`.", file=sys.stderr)
        return 1

    _prior_number, prior_body, _prior_url = read_ledger(host, repo_full)
    since, source = resolve_since(args.since, prior_body, _dt.date.today())

    out_dir = Path(args.out_dir or (Path(tempfile.gettempdir()) / f"learning-log-{today}"))
    out_dir.mkdir(parents=True, exist_ok=True)

    siblings = list_sibling_repos(host, owner)
    repos = sorted(set(siblings) | {_repo})
    all_prs: list[dict] = []
    all_issues: list[dict] = []
    for repo in repos:
        prs, issues = gather_repo(host, owner, repo, since)
        all_prs += prs
        all_issues += issues
        if prs or issues:
            print(f"  {repo}: {len(prs)} PRs/MRs, {len(issues)} issues", file=sys.stderr)

    stats = compute_stats(all_prs, all_issues)
    stats_md = render_stats(stats, since, today)
    stats_file = out_dir / "stats.md"
    stats_file.write_text(stats_md, encoding="utf-8")

    (out_dir / "prior-horizon.md").write_text(
        slice_section(prior_body, HORIZON_HEADER) or "(none -- first run, no prior horizon to grade)",
        encoding="utf-8")

    manifest = write_bucket_files(out_dir, all_prs, all_issues)

    t = stats["total"]
    print(f"HOST={host}")
    print(f"REPO_FULL={repo_full}")
    print(f"SINCE={since}")
    print(f"SINCE_SOURCE={source}")
    print(f"OUT_DIR={out_dir}")
    print(f"STATS_FILE={stats_file}")
    print(f"PRIOR_HORIZON_FILE={out_dir / 'prior-horizon.md'}")
    print(f"TOTALS=PRs={t['prs']} issues={t['issues']} add={t['add']} del={t['del']} repos={len(repos)}")
    for bucket, slug, npr, nis, path in manifest:
        print(f"BUCKET={slug}|{bucket}|prs={npr}|issues={nis}|file={path}")
    print()
    print(stats_md)
    return 0


def cmd_assemble_ledger(args) -> int:
    today = _dt.date.today().isoformat()
    host, _owner, _repo, repo_full = resolve_repo_context()
    _number, prior_body, _url = read_ledger(host, repo_full) if repo_full else (None, "", None)
    horizon = Path(args.horizon_file).read_text(encoding="utf-8") if args.horizon_file else ""
    discoveries = Path(args.discoveries_file).read_text(encoding="utf-8") if args.discoveries_file else ""
    body = build_ledger_body(prior_body, today, horizon, discoveries)
    Path(args.out).write_text(body, encoding="utf-8")
    print(args.out)
    return 0


def cmd_upsert_ledger(args) -> int:
    host, _owner, _repo, repo_full = resolve_repo_context()
    if not repo_full:
        print("Could not resolve owner/repo from `git remote get-url origin`.", file=sys.stderr)
        return 1
    body = Path(args.body_file).read_text(encoding="utf-8")
    number, url = upsert_ledger(host, repo_full, body)
    if not number:
        print("Ledger upsert failed -- no issue number returned.", file=sys.stderr)
        return 1
    print(f"LEDGER_NUMBER={number}")
    print(f"LEDGER_URL={url or ''}")
    return 0


def cmd_comment(args) -> int:
    host, _owner, _repo, repo_full = resolve_repo_context()
    if not repo_full:
        print("Could not resolve owner/repo from `git remote get-url origin`.", file=sys.stderr)
        return 1
    url = post_comment(host, repo_full, args.issue, args.body_file)
    if not url:
        print("Comment post failed.", file=sys.stderr)
        return 1
    print(f"COMMENT_URL={url}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Gather + bucket + stat the sibling-repo work stream for /learning-log.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("probe")

    g = sub.add_parser("gather")
    g.add_argument("--since")
    g.add_argument("--out-dir", dest="out_dir", default=None)

    a = sub.add_parser("assemble-ledger")
    a.add_argument("--horizon-file", dest="horizon_file")
    a.add_argument("--discoveries-file", dest="discoveries_file")
    a.add_argument("--out", required=True)

    u = sub.add_parser("upsert-ledger")
    u.add_argument("--body-file", dest="body_file", required=True)

    c = sub.add_parser("comment")
    c.add_argument("--issue", type=int, required=True)
    c.add_argument("--body-file", dest="body_file", required=True)

    args = ap.parse_args(argv)
    return {
        "probe": cmd_probe,
        "gather": cmd_gather,
        "assemble-ledger": cmd_assemble_ledger,
        "upsert-ledger": cmd_upsert_ledger,
        "comment": cmd_comment,
    }[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
