"""Hermetic tests for skills/prompt-audit/audit.py (stdlib unittest).

Run:  python -m unittest discover -s tests -v

No network and no gh/glab: the one subprocess seam (`_run`) is stubbed wherever a
CLI would be spawned. One test reads the private fleet-config tool from a local
checkout to prove ledger compatibility and skips cleanly where that checkout is
absent (for example on a work machine).
"""

from __future__ import annotations

import importlib.util
import io
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1] / "skills" / "prompt-audit"
PRIVATE_AUDIT = Path("E:/automation/fleet-config-wt-834/.claude/skills/prompt-audit/audit.py")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(module)
    return module


pa = _load("lite_prompt_audit", SKILL_DIR / "audit.py")
RULES = pa.parse_rules(pa.RULES_MD.read_text(encoding="utf-8"))
AUD = pa.load_toml()["audiences"]


def plan_line(key: str, action: str = "scan", sha: str = "aaaaaaaaaaaa") -> str:
    return f"PLAN={key}|action={action}|reason=new|sha={sha}"


class StubRunner:
    """Records every argv passed to `_run` and answers with canned output."""

    def __init__(self, stdout: str = "[]", returncode: int = 0):
        self.calls: list[list[str]] = []
        self.stdout, self.returncode = stdout, returncode

    def __call__(self, cmd, cwd=None, timeout=120):
        self.calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, self.returncode, stdout=self.stdout, stderr="")


class StubbedRunnerCase(unittest.TestCase):
    def stub(self, runner: StubRunner) -> StubRunner:
        original = pa._run
        pa._run = runner
        self.addCleanup(setattr, pa, "_run", original)
        return runner


class CapTests(unittest.TestCase):
    def _entries(self, repos: list[str]) -> list:
        return [pa.Entry(key=f"{r}/CLAUDE.md", path=Path(r), repo=r, kind="claude-md", data=b"x") for r in repos]

    def test_caps_are_the_documented_values(self):
        self.assertEqual(pa.MAX_REPOS_PER_RUN, 2)
        self.assertEqual(pa.MAX_FINDINGS_PER_FILE, 5)

    def test_auto_selection_takes_at_most_two_repos_and_defers_the_rest(self):
        entries = self._entries(["a", "b", "c", "d"])
        plan = {e.key: ("scan", "new") for e in entries}
        plan["a/CLAUDE.md"] = ("skip", "unchanged")
        chosen, deferred = pa.select_repos(entries, plan)
        self.assertEqual(chosen, ["b", "c"])
        self.assertEqual(deferred, {"d": 1})

    def test_explicit_request_over_the_cap_is_refused(self):
        entries = self._entries(["a", "b", "c"])
        plan = {e.key: ("scan", "new") for e in entries}
        with self.assertRaises(pa.CapError):
            pa.select_repos(entries, plan, requested=["a", "b", "c"])
        self.assertEqual(pa.select_repos(entries, plan, requested=["c", "c"])[0], ["c"])

    def test_digest_and_ledger_refuse_a_run_over_the_repo_cap(self):
        run = {"scan_ran": True, "plan": [plan_line(f"{r}/CLAUDE.md") for r in "abc"], "judgments": {}}
        with self.assertRaises(pa.CapError):
            pa.render_digest(run, RULES)
        with self.assertRaises(pa.CapError):
            pa.partition_run(run)

    def test_findings_per_file_capped_violations_first(self):
        findings = ([{"rule": "R-13", "verdict": "consider", "line": i} for i in range(1, 5)]
                    + [{"rule": "R-03", "verdict": "violation", "line": 40 + i} for i in range(3)]
                    + [{"rule": "R-18", "verdict": "unmeasured", "line": None}])
        kept, dropped = pa.cap_findings(findings)
        self.assertEqual(len(kept), 5)
        self.assertEqual(dropped, 2)
        self.assertEqual([f["verdict"] for f in kept[:3]], ["violation"] * 3)

        run = {"date": "2026-09-13", "scan_ran": True, "plan": [plan_line("a/CLAUDE.md")],
               "judgments": {"a/CLAUDE.md": findings}}
        parts = pa.partition_run(run)
        self.assertEqual(len(parts["findings"]), 5)
        self.assertEqual(parts["capped"], {"a/CLAUDE.md": 2})
        body, status = pa.render_digest(run, RULES)
        self.assertIn("Held back by the 5-findings-per-file cap", body)
        self.assertEqual(status, "partial")  # the unmeasured rule is never folded into complete

    def test_no_scheduler_or_notification_surface(self):
        self.assertFalse((SKILL_DIR / "run-weekly.bat").exists())
        skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("serially", skill)
        self.assertNotRegex(skill.lower(), r"telegram|slack")


class LedgerTests(unittest.TestCase):
    FILES = {"repo-a/CLAUDE.md": "0123456789ab", "home/skills/x/SKILL.md": "ba9876543210"}

    def _body(self) -> str:
        rubric = pa.rules_rubric()
        body = pa.render_ledger_body(self.FILES, rubric, "2026-09-13", pa.load_toml()["sources"])
        return pa.ensure_marker(body, pa.KIND)

    def test_render_parse_roundtrip_and_identity(self):
        body = self._body()
        self.assertEqual(pa.parse_ledger(body),
                         {"rubric": pa.rules_rubric(), "run_at": "2026-09-13", "files": self.FILES})
        self.assertTrue(body.startswith("<!-- audit-managed: kind=prompt-audit -->\n"))
        self.assertEqual(pa.pick_ledger([{"number": 8, "title": "prompt-audit ledger", "body": ""},
                                         {"number": 5, "title": "x", "body": body},
                                         {"number": 3, "title": "codebase-audit ledger", "body": ""}]), (5, [8]))

    def test_private_tool_reads_a_lite_written_ledger_unchanged(self):
        if not PRIVATE_AUDIT.is_file():
            self.skipTest(f"private fleet-config checkout not present at {PRIVATE_AUDIT} (expected on a work machine)")
        before = list(sys.path)
        try:
            private = _load("private_prompt_audit", PRIVATE_AUDIT)
            audit_issue = sys.modules["audit_issue"]
        finally:
            sys.path[:] = before
        body = self._body()
        self.assertEqual(private.parse_ledger(body),
                         {"rubric": pa.rules_rubric(), "run_at": "2026-09-13", "files": self.FILES})
        self.assertEqual(private.rules_rubric(), pa.rules_rubric())
        self.assertTrue(audit_issue.has_marker(body, "prompt-audit"))
        self.assertTrue(audit_issue.title_matches(pa.TITLE, "prompt-audit"))

    def test_plan_skips_only_under_the_same_rubric(self):
        ledger = pa.parse_ledger(self._body())
        current = {"repo-a/CLAUDE.md": "0123456789ab", "repo-a/AGENTS.md": "ffffffffffff", "repo-a/x.md": "unmeasured"}
        plan = pa.plan_scan(current, ledger, pa.rules_rubric())
        self.assertEqual(plan["repo-a/CLAUDE.md"], ("skip", "unchanged"))
        self.assertEqual(plan["repo-a/AGENTS.md"], ("scan", "new"))
        self.assertEqual(plan["repo-a/x.md"], ("unmeasured", "unreadable"))
        self.assertEqual(pa.plan_scan(current, ledger, "other")["repo-a/CLAUDE.md"], ("scan", "rubric-changed"))


class HostTests(StubbedRunnerCase):
    def test_detection_from_origin_urls(self):
        cases = {
            "https://github.com/o/r.git": ("github", "gh", "o/r"),
            "git@github.com:o/r.git": ("github", "gh", "o/r"),
            "https://gitlab.com/example-group/example-repo.git": ("gitlab", "glab", "example-group/example-repo"),
            "git@gitlab.example.com:grp/sub/proj.git": ("gitlab", "glab", "grp/sub/proj"),
        }
        for url, (host, cli, repo) in cases.items():
            self.assertEqual((pa.detect_host(url), pa.cli_for(pa.detect_host(url)), pa.parse_owner_repo(url)),
                             (host, cli, repo), url)

    def test_resolve_repo_reads_origin(self):
        runner = self.stub(StubRunner(stdout="https://gitlab.com/example-group/example-repo.git\n"))
        self.assertEqual(pa.resolve_repo(Path(".")), ("gitlab", "example-group/example-repo"))
        self.assertEqual(runner.calls[0], ["git", "remote", "get-url", "origin"])

    def test_gitlab_origin_drives_glab(self):
        runner = self.stub(StubRunner(stdout='[{"iid": 4, "title": "prompt-audit ledger", "description": "", "state": "opened"}]'))
        ledger = pa.read_ledger("gitlab", "example-group/example-repo")
        self.assertEqual(ledger["number"], 4)
        self.assertEqual(runner.calls[0][0], "glab")
        self.assertIn("--output", runner.calls[0])

        runner.calls.clear()
        runner.stdout = "https://gitlab.com/example-group/example-repo/-/issues/9"
        pa.upsert_ledger("gitlab", "example-group/example-repo", None, "body", dry_run=False)
        self.assertTrue(all(c[0] == "glab" for c in runner.calls))
        self.assertTrue(any(c[1:3] == ["issue", "create"] and "--description-file" in c for c in runner.calls))

    def test_github_origin_drives_gh(self):
        runner = self.stub(StubRunner(stdout="[]"))
        pa.read_ledger("github", "o/r")
        self.assertEqual(runner.calls[0][0], "gh")

    def test_dry_run_spawns_no_write(self):
        runner = self.stub(StubRunner(stdout="[]"))
        out = io.StringIO()
        with redirect_stdout(out):
            pa.upsert_ledger("gitlab", "example-group/example-repo", None, "body", dry_run=True)
            pa._write("gitlab", pa.comment_args("gitlab", "g/r", 4, "digest.md"), dry_run=True)
        self.assertEqual(runner.calls, [])
        argvs = [l for l in out.getvalue().splitlines() if l.startswith("ARGV=")]
        self.assertTrue(argvs and all(l.startswith("ARGV=glab ") for l in argvs), argvs)

    def test_unreadable_ledger_is_reported_not_empty_success(self):
        self.stub(StubRunner(stdout="", returncode=1))
        ledger = pa.read_ledger("gitlab", "g/r")
        self.assertIsNone(ledger["number"])
        self.assertTrue(ledger["error"])


class FreshnessAndDigestTests(unittest.TestCase):
    CFG = {"marker_kind": "none", "baseline_sha": "abc", "baseline_marker": ""}

    def test_unfetched_source_is_never_unchanged(self):
        for data in (None, b""):
            self.assertEqual(pa.diff_source(self.CFG, data)["verdict"], "not-checked")
        self.assertEqual(pa.diff_source({**self.CFG, "baseline_sha": pa.sha12(b"x")}, b"x")["verdict"], "unchanged")

    def test_not_checked_digest_says_not_checked(self):
        run = {"date": "2026-09-13", "scan_ran": True, "plan": [],
               "sources": ["VERDICT=not-checked|id=s1|sha=unmeasured|marker=unmeasured|reason=fetch failed"]}
        body, status = pa.render_digest(run, RULES)
        self.assertIn("`guides=not-checked`", body)
        self.assertIn("unchanged 0", body)
        self.assertEqual(status, "complete")

    def test_stamp_line_present_and_ascii(self):
        for scan_ran, dry, expect in ((True, False, "posted"), (True, True, "dry-run"), (False, False, "not-run")):
            run = {"date": "2026-09-13", "scan_ran": scan_ran, "dry_run": dry, "plan": [plan_line("a/CLAUDE.md")],
                   "judgments": {"a/CLAUDE.md": []},
                   "sources": ["VERDICT=changed|id=s1|sha=x|marker=none|reason=sha moved"]}
            body, status = pa.render_digest(run, RULES)
            stamp = body.splitlines()[1]
            self.assertRegex(stamp, rf"^<!-- prompt-audit-digest run=2026-09-13 status={status} scan={expect} "
                                    r"update-issue=none -->$")
            self.assertTrue(stamp.isascii())

    def test_unjudged_planned_file_is_unmeasured(self):
        run = {"date": "d", "scan_ran": True, "plan": [plan_line("a/CLAUDE.md"), plan_line("a/AGENTS.md")],
               "judgments": {"a/CLAUDE.md": []}}
        parts = pa.partition_run(run)
        self.assertEqual(parts["unmeasured"], ["a/AGENTS.md"])
        self.assertEqual(set(parts["recorded"]), {"a/CLAUDE.md"})
        self.assertEqual(pa.render_digest(run, RULES)[1], "partial")


class InventoryAndLintTests(unittest.TestCase):
    def test_siblings_exclude_worktrees_and_non_repos(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for name in ("home", "repo-a", "repo-a-wt-3", "linked"):
                (root / name).mkdir()
            for name in ("home", "repo-a", "repo-a-wt-3"):
                (root / name / ".git").mkdir()
            (root / "linked" / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
            (root / "plain").mkdir()
            self.assertEqual(sorted(pa.fleet_repos(root / "home")), ["home", "repo-a"])

            (root / "home" / "global-instructions.md").write_text("# G\n\nKeep it small.\n", encoding="utf-8")
            (root / "home" / "skills" / "s").mkdir(parents=True)
            (root / "home" / "skills" / "s" / "SKILL.md").write_text("---\nname: s\ndescription: Does x.\n---\n", encoding="utf-8")
            (root / "repo-a" / ".github").mkdir()
            (root / "repo-a" / ".github" / "copilot-instructions.md").write_text("x\n", encoding="utf-8")
            (root / "repo-a" / "CLAUDE.md").write_text("x\n", encoding="utf-8")
            keys = [e.key for e in pa.inventory(pa.fleet_repos(root / "home"), AUD, "home")]
            self.assertEqual(keys[0], "home/global-instructions.md")
            self.assertEqual(set(keys), {"home/global-instructions.md", "home/skills/s/SKILL.md",
                                         "repo-a/CLAUDE.md", "repo-a/.github/copilot-instructions.md"})

    def test_lint_counts_and_caps(self):
        text = "# T\n\nYou MUST run it.\nPlease double-check your work.\n```\nNEVER inside a fence\n```\n"
        entry = pa.Entry(key="r/AGENTS.md", path=Path("x"), repo="r", kind="agents-md", data=text.encode())
        res = pa.lint_entry(entry, RULES, AUD)
        self.assertEqual(res.counts().get("R-01"), 1)  # the fenced NEVER is not linted
        self.assertEqual(next(h.cap for h in res.hits if h.rule == "R-01"), "consider")
        self.assertEqual(next(h.cap for h in res.hits if h.rule == "R-03"), "violation")


class ContractTests(unittest.TestCase):
    VENDOR_WORDS = re.compile(r"anthropic|openai|claude|codex|gpt|opus|sonnet|haiku|fable|mythos|astra|gemini|copilot", re.I)
    FILE_CONVENTIONS = re.compile(r"global-CLAUDE\.md|CLAUDE\.md|\.claude/|\.claude\b|claude-md|copilot-instructions\.md")

    def test_rule_set_and_sources_are_present_and_parse(self):
        self.assertEqual(len(RULES), 29)
        # Build both variants from LF-normalised bytes: an autocrlf=true checkout already has CRLF on disk.
        lf = pa.RULES_MD.read_bytes().replace(b"\r\n", b"\n")
        self.assertEqual(pa.rules_rubric(lf.replace(b"\n", b"\r\n")), pa.rules_rubric(lf))
        self.assertEqual(pa.rules_rubric(), pa.rules_rubric(lf))
        self.assertTrue(pa.load_toml()["sources"])

    def test_skill_and_helper_name_no_vendor_or_model(self):
        for name in ("SKILL.md", "audit.py"):
            lines = (SKILL_DIR / name).read_text(encoding="utf-8").splitlines()
            hits = [l for l in lines if self.VENDOR_WORDS.search(self.FILE_CONVENTIONS.sub("", l))]
            self.assertEqual(hits, [], name)

    def test_helper_is_self_contained(self):
        src = (SKILL_DIR / "audit.py").read_text(encoding="utf-8")
        self.assertNotRegex(src, r"(?m)^\s*(?:from|import)\s+(?:_lib|git_run|audit_issue|no_window)\b")
        self.assertNotIn("sys.path.insert", src)
        self.assertEqual(src.count("subprocess.run("), 1)
        self.assertIn("creationflags=NO_WINDOW", src)


if __name__ == "__main__":
    unittest.main()
