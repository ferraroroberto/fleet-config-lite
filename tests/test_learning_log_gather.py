"""Hermetic tests for skills/learning-log/gather.py (stdlib unittest, no deps).

Run:  python -m unittest discover -s tests -v

Covers the pure functions -- host/owner parsing, bucketing, stats,
ledger-body assembly -- plus the gh/glab-calling ledger functions with
subprocess mocked out (no live network/GitHub/GitLab writes).
"""

from __future__ import annotations

import datetime as _dt
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SKILL_DIR = Path(__file__).resolve().parents[1] / "skills" / "learning-log"
sys.path.insert(0, str(SKILL_DIR))

import gather as gl  # noqa: E402


class OwnerRepoParsingTests(unittest.TestCase):
    def test_https_github(self):
        self.assertEqual(
            gl.parse_owner_repo("https://github.com/ferraroroberto/fleet-config-lite.git"),
            ("ferraroroberto", "fleet-config-lite"))

    def test_ssh_github(self):
        self.assertEqual(
            gl.parse_owner_repo("git@github.com:ferraroroberto/fleet-config-lite.git"),
            ("ferraroroberto", "fleet-config-lite"))

    def test_https_gitlab_subgroup(self):
        self.assertEqual(
            gl.parse_owner_repo("https://gitlab.example.com/group/subgroup/project.git"),
            ("group/subgroup", "project"))

    def test_ssh_gitlab(self):
        self.assertEqual(
            gl.parse_owner_repo("git@gitlab.com:group/project.git"),
            ("group", "project"))

    def test_empty_or_malformed(self):
        self.assertEqual(gl.parse_owner_repo(""), ("", ""))
        self.assertEqual(gl.parse_owner_repo("not-a-url"), ("", ""))


class HostDetectionTests(unittest.TestCase):
    def test_github(self):
        self.assertEqual(gl.detect_host("https://github.com/a/b.git"), "github")

    def test_gitlab_com(self):
        self.assertEqual(gl.detect_host("https://gitlab.com/a/b.git"), "gitlab")

    def test_self_hosted_gitlab(self):
        self.assertEqual(gl.detect_host("git@gitlab.corp.internal:a/b.git"), "gitlab")

    def test_empty_defaults_to_gitlab(self):
        self.assertEqual(gl.detect_host(""), "gitlab")


class SinceResolutionTests(unittest.TestCase):
    def test_explicit_arg_wins(self):
        since, source = gl.resolve_since("2026-01-01", "last-run-at: 2026-05-01", _dt.date(2026, 8, 5))
        self.assertEqual((since, source), ("2026-01-01", "arg"))

    def test_falls_back_to_ledger(self):
        since, source = gl.resolve_since(None, "last-run-at: 2026-05-01", _dt.date(2026, 8, 5))
        self.assertEqual((since, source), ("2026-05-01", "ledger"))

    def test_falls_back_to_trailing_week(self):
        since, source = gl.resolve_since(None, "", _dt.date(2026, 8, 5))
        self.assertEqual((since, source), ("2026-07-29", "default"))


class BucketingTests(unittest.TestCase):
    def test_pr_bucket_from_conventional_prefix(self):
        self.assertEqual(gl.pr_bucket("feat: add widget"), "Features & enhancements")
        self.assertEqual(gl.pr_bucket("fix(ui): broken button"), "Bug fixes")
        self.assertEqual(gl.pr_bucket("docs: update readme"), "Documentation")
        self.assertEqual(gl.pr_bucket("no prefix here"), "Other")

    def test_issue_bucket_from_labels(self):
        self.assertEqual(gl.issue_bucket(["bug", "help wanted"]), "Bug fixes")
        self.assertEqual(gl.issue_bucket(["enhancement"]), "Features & enhancements")
        self.assertEqual(gl.issue_bucket(["wontfix"]), "Other")


class StatsTests(unittest.TestCase):
    def test_compute_stats_totals(self):
        prs = [
            {"repo": "a", "additions": 10, "deletions": 2, "bucket": "Bug fixes"},
            {"repo": "b", "additions": 5, "deletions": 1, "bucket": "Features & enhancements"},
        ]
        issues = [{"repo": "a", "bucket": "Bug fixes"}]
        stats = gl.compute_stats(prs, issues)
        self.assertEqual(stats["total"], {"prs": 2, "issues": 1, "add": 15, "del": 3})
        self.assertEqual(stats["repos"]["a"], {"prs": 1, "issues": 1, "add": 10, "del": 2})
        self.assertEqual(stats["buckets"]["Bug fixes"]["prs"], 1)
        self.assertEqual(stats["buckets"]["Bug fixes"]["issues"], 1)

    def test_render_stats_includes_grand_total_row(self):
        stats = gl.compute_stats(
            [{"repo": "a", "additions": 100, "deletions": 0, "bucket": "Other"}], [])
        out = gl.render_stats(stats, "2026-08-01", "2026-08-05")
        self.assertIn("**TOTAL**", out)
        self.assertIn("+100", out)


class WriteBucketFilesTests(unittest.TestCase):
    def test_writes_one_file_per_nonempty_bucket(self):
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td)
            prs = [{"repo": "a", "number": 1, "title": "feat: x", "additions": 3, "deletions": 1,
                    "bucket": "Features & enhancements"}]
            issues = [{"repo": "a", "number": 2, "title": "bug y", "labels": ["bug"],
                       "bucket": "Bug fixes"}]
            manifest = gl.write_bucket_files(out_dir, prs, issues)
            slugs = {m[1] for m in manifest}
            self.assertEqual(slugs, {"features-enhancements", "bug-fixes"})
            for _bucket, _slug, _npr, _nis, path in manifest:
                self.assertTrue(path.is_file())


class LedgerBodyTests(unittest.TestCase):
    def test_first_run_no_prior_body(self):
        body = gl.build_ledger_body("", "2026-08-05", "- [ ] do the thing", "- discovered X")
        self.assertIn(gl.STATE_MARKER, body)
        self.assertIn("last-run-at: 2026-08-05", body)
        self.assertIn("- [ ] do the thing", body)
        self.assertIn("2026-08-05: discovered X", body)

    def test_preserves_prior_archive(self):
        prior = (
            f"{gl.STATE_MARKER}\nlast-run-at: 2026-07-29\n\n"
            f"{gl.ARCHIVE_HEADER}\n- 2026-07-29: old lesson\n"
        )
        body = gl.build_ledger_body(prior, "2026-08-05", "", "- new lesson")
        self.assertIn("2026-08-05: new lesson", body)
        self.assertIn("2026-07-29: old lesson", body)

    def test_parse_last_run_roundtrip(self):
        body = gl.build_ledger_body("", "2026-08-05", "", "")
        self.assertEqual(gl.parse_last_run(body), "2026-08-05")


class LedgerCliTests(unittest.TestCase):
    """Ledger read/upsert/comment against a mocked CLI layer -- no live writes."""

    def test_read_ledger_github_finds_labeled_issue(self):
        with patch.object(gl, "_cli_json", return_value=[
            {"number": 7, "body": "old body", "url": "https://github.com/o/r/issues/7"}]):
            number, body, url = gl.read_ledger("github", "o/r")
        self.assertEqual((number, body, url), (7, "old body", "https://github.com/o/r/issues/7"))

    def test_read_ledger_none_found(self):
        with patch.object(gl, "_cli_json", return_value=[]):
            number, body, url = gl.read_ledger("github", "o/r")
        self.assertEqual((number, body, url), (None, "", None))

    def test_upsert_ledger_edits_when_issue_exists(self):
        calls = []

        def fake_run(cmd, timeout=120):
            calls.append(cmd)
            class R:
                returncode = 0
                stdout = ""
            return R()

        with patch.object(gl, "ensure_ledger_label"), \
             patch.object(gl, "read_ledger", return_value=(7, "old", "https://github.com/o/r/issues/7")), \
             patch.object(gl, "_run", side_effect=fake_run), \
             patch.object(gl, "_cli_json", return_value={"url": "https://github.com/o/r/issues/7"}):
            number, url = gl.upsert_ledger("github", "o/r", "new body")
        self.assertEqual(number, 7)
        self.assertEqual(url, "https://github.com/o/r/issues/7")
        self.assertTrue(any(c[:3] == ["gh", "issue", "edit"] for c in calls))
        self.assertFalse(any(c[:3] == ["gh", "issue", "create"] for c in calls))

    def test_upsert_ledger_creates_when_no_issue_exists(self):
        def fake_run(cmd, timeout=120):
            class R:
                returncode = 0
                stdout = "https://github.com/o/r/issues/9\n" if cmd[:3] == ["gh", "issue", "create"] else ""
            return R()

        with patch.object(gl, "ensure_ledger_label"), \
             patch.object(gl, "read_ledger", return_value=(None, "", None)), \
             patch.object(gl, "_run", side_effect=fake_run):
            number, url = gl.upsert_ledger("github", "o/r", "new body")
        self.assertEqual(number, 9)
        self.assertEqual(url, "https://github.com/o/r/issues/9")

    def test_post_comment_returns_url_on_success(self):
        def fake_run(cmd, timeout=120):
            class R:
                returncode = 0
                stdout = "https://github.com/o/r/issues/7#issuecomment-1\n"
            return R()

        with patch.object(gl, "_run", side_effect=fake_run):
            url = gl.post_comment("github", "o/r", 7, "body.md")
        self.assertEqual(url, "https://github.com/o/r/issues/7#issuecomment-1")

    def test_post_comment_returns_none_on_failure(self):
        def fake_run(cmd, timeout=120):
            class R:
                returncode = 1
                stdout = ""
            return R()

        with patch.object(gl, "_run", side_effect=fake_run):
            url = gl.post_comment("github", "o/r", 7, "body.md")
        self.assertIsNone(url)


if __name__ == "__main__":
    unittest.main()
