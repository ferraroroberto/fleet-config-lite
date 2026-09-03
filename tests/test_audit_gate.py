"""Hermetic tests for skills/codebase-audit/audit_gate.py (stdlib unittest).

Run:  python -m unittest discover -s tests -v

Pure helpers (decision, ledger parse/render, marker identity, numstat
weighting, self-fix detection) run with no git or gh/glab. One integration
case builds a real throwaway git repo to prove significance_since counts
source lines, ignores docs/tests, and skips self-fix commits.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1] / "skills" / "codebase-audit"
sys.path.insert(0, str(SKILL_DIR))

import audit_gate as ag  # noqa: E402


class DecisionTests(unittest.TestCase):
    def test_unknowns_fail_open(self):
        self.assertEqual(ag.decide(None, "r", "r"), "AUDIT")
        self.assertEqual(ag.decide(3, None, "r"), "AUDIT")

    def test_zero_commits_rubric_decides(self):
        self.assertEqual(ag.decide(0, "r", "r"), "SKIP")
        self.assertEqual(ag.decide(0, "r", "changed"), "AUDIT")

    def test_self_fix_skips_even_when_rubric_changed(self):
        self.assertEqual(ag.decide(2, "r", "changed", self_fix=True), "SKIP_SELF_FIX")

    def test_threshold(self):
        self.assertEqual(ag.decide(5, "r", "r", significance=999), "SKIP_BELOW_THRESHOLD")
        self.assertEqual(ag.decide(5, "r", "r", significance=1000), "AUDIT")
        self.assertEqual(ag.decide(5, "r", "r", significance=50, threshold=40), "AUDIT")
        self.assertEqual(ag.decide(5, "r", "r", significance=None), "AUDIT")


class LedgerTests(unittest.TestCase):
    def test_render_then_parse_roundtrip(self):
        body = ag.render_ledger_body("abc123", "2026-09-03", "")
        self.assertIn(ag._LEDGER_MARKER, body)
        self.assertEqual(ag.parse_ledger(body), {"sha": "abc123", "at": "2026-09-03", "rubric": ""})

    def test_parse_matches_private_tool_block(self):
        # The exact body the private fleet-config tool wrote into this repo's issue #9.
        body = ("<!-- audit-managed: kind=ledger -->\r\n\r\nMachine-readable ledger …\r\n\r\n"
                "<!-- audit-ledger -->\r\nlast-audited-sha: 44550550c336e7b52e720258c8335f8177509b55\r\n"
                "last-audited-at: 2026-08-20\r\nrubric-sha: \r\n")
        parsed = ag.parse_ledger(body)
        self.assertEqual(parsed["sha"], "44550550c336e7b52e720258c8335f8177509b55")
        self.assertEqual(parsed["at"], "2026-08-20")
        self.assertEqual(parsed["rubric"], "")

    def test_open_comment_form_and_missing(self):
        self.assertEqual(ag.parse_ledger("<!-- audit-ledger\nlast-audited-sha: x\nrubric-sha: r\n-->")["sha"], "x")
        self.assertEqual(ag.parse_ledger("no block here"), {"sha": None, "at": None, "rubric": None})


class MarkerTests(unittest.TestCase):
    def test_marker_only_on_first_line(self):
        self.assertTrue(ag.has_marker("<!-- audit-managed: kind=slop -->\n\nbody", "slop"))
        self.assertFalse(ag.has_marker("prose quoting <!-- audit-managed: kind=slop -->", "slop"))
        self.assertFalse(ag.has_marker("<!-- audit-managed: kind=slop -->", "bug"))

    def test_ensure_marker_idempotent(self):
        once = ag.ensure_marker("hello", "bug")
        self.assertEqual(ag.ensure_marker(once, "bug"), once)
        self.assertEqual(once.count("audit-managed"), 1)

    def test_plan_keeps_lowest_and_adopts_by_title(self):
        issues = [{"number": 7, "title": "audit: bug findings (3 items)", "body": ""},
                  {"number": 3, "title": "x", "body": "<!-- audit-managed: kind=bug -->\n"},
                  {"number": 9, "title": "codebase-audit ledger", "body": ""}]
        self.assertEqual(ag.plan(issues, "bug"), (3, [7]))
        self.assertEqual(ag.plan(issues, "ledger"), (9, []))
        self.assertEqual(ag.plan(issues, "stale"), (None, []))
        self.assertEqual(ag.managed_numbers(issues), {3, 7})


class SignificanceHelpersTests(unittest.TestCase):
    def test_source_path_filter(self):
        for p in ("src/app.py", "hooks/x.ps1", "install.ps1", "web/static/app.js"):
            self.assertTrue(ag.is_source_path(p), p)
        for p in ("README.md", "docs/guide.md", "docs/x.py", "tests/test_x.py", "src/test_app.py",
                  "pkg/app_test.go", "package-lock.json", "poetry.lock", "notes.txt"):
            self.assertFalse(ag.is_source_path(p), p)

    def test_numstat_weights_and_binary_rows(self):
        text = "10\t5\tsrc/app.py\n100\t0\tREADME.md\n-\t-\timg/logo.png\n3\t1\ttests/test_app.py\n7\t2\tskills/x.py\n"
        self.assertEqual(ag.parse_numstat(text), 15 + 9)

    def test_references_managed(self):
        managed = {12, 30}
        self.assertTrue(ag.references_managed("fix: prune dead helpers\n\nCloses #12", managed))
        self.assertTrue(ag.references_managed("Merge branch 'chore/30-slop-cleanup' into main", managed))
        self.assertFalse(ag.references_managed("feat: new thing (#44)", managed))
        self.assertFalse(ag.references_managed("see https://x/issues/12/#12", {99}))

    def test_parse_owner_repo_and_host(self):
        self.assertEqual(ag.parse_owner_repo("https://github.com/o/r.git"), "o/r")
        self.assertEqual(ag.parse_owner_repo("git@gitlab.example.com:grp/sub/proj.git"), "grp/sub/proj")
        self.assertEqual(ag.parse_owner_repo("nonsense"), "")
        self.assertEqual(ag.detect_host("https://github.com/o/r"), "github")
        self.assertEqual(ag.detect_host("git@gitlab.example.com:g/p.git"), "gitlab")


class GitIntegrationTests(unittest.TestCase):
    """A throwaway repo: baseline → docs-only commit → self-fix commit → source commit."""

    def _git(self, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=self.repo, capture_output=True, text=True,
                              check=True, creationflags=ag.NO_WINDOW).stdout.strip()

    def _commit(self, name: str, lines: int, message: str) -> str:
        p = Path(self.repo) / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(f"line {i}" for i in range(lines)) + "\n", encoding="utf-8")
        self._git("add", "-A")
        self._git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", message)
        return self._git("rev-parse", "HEAD")

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.repo = self._td.name
        subprocess.run(["git", "init", "-q", "-b", "main", self.repo], check=True, creationflags=ag.NO_WINDOW)
        # A user-level core.hooksPath (author allowlists, signing) must not reach a throwaway repo.
        self._git("config", "core.hooksPath", str(Path(self.repo) / "no-hooks"))
        self._git("config", "core.autocrlf", "false")
        self.base = self._commit("src/app.py", 10, "feat: initial")

    def tearDown(self):
        self._td.cleanup()

    def test_significance_counts_only_organic_source_lines(self):
        self._commit("docs/guide.md", 500, "docs: big guide")
        self._commit("src/helpers.py", 40, "fix: drop dead helpers\n\nCloses #12")
        self._commit("src/core.py", 25, "feat: core module")
        shas = ag.commits_since(self.repo, self.base)
        self.assertEqual(len(shas), 3)
        organic, total = ag.significance_since(self.repo, shas, managed={12})
        self.assertEqual(len(organic), 2)  # docs commit is organic but weighs 0
        self.assertEqual(total, 25)
        self.assertEqual(ag.decide(3, "", "", self_fix=False, significance=total), "SKIP_BELOW_THRESHOLD")
        self.assertEqual(ag.decide(3, "", "", self_fix=False, significance=total, threshold=20), "AUDIT")

    def test_self_fix_only_and_baseline_checks(self):
        self._commit("src/helpers.py", 4, "fix: prune (#12)")
        shas = ag.commits_since(self.repo, self.base)
        organic, _ = ag.significance_since(self.repo, shas, managed={12})
        self.assertEqual(organic, [])
        self.assertTrue(ag.sha_reachable(self.repo, self.base))
        self.assertFalse(ag.sha_reachable(self.repo, "0" * 40))
        self.assertIsNone(ag.commits_since(self.repo, "0" * 40))
        self.assertEqual(ag.default_branch_sha(self.repo), self._git("rev-parse", "HEAD"))


if __name__ == "__main__":
    unittest.main()
