"""Tests for `chief_ops.py merge`: GitLab's state is the verdict; a refusal can become a plan question.

Run:  python -m unittest discover -s tests -v

glab is a fake runner scripted per subcommand, so every verdict is driven
without a GitLab project; the plan file lives in a temp state dir.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skills" / "_lib"))

from chief import lite_merge  # noqa: E402


def fake_glab(merge_rc: int, state: str, stderr: str = "", view_rc: int = 0, status: str = ""):
    calls = []

    def run(args):
        calls.append(args)
        if args[:2] == ["mr", "merge"]:
            return subprocess.CompletedProcess(args, merge_rc, stdout="", stderr=stderr)
        body = json.dumps({"iid": 7, "state": state, "detailed_merge_status": status,
                           "web_url": "https://gitlab.example/demo/-/merge_requests/7"})
        return subprocess.CompletedProcess(args, view_rc, stdout=body, stderr="view failed" if view_rc else "")

    run.calls = calls
    return run


class MergeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.state = Path(self._td.name)
        patcher = mock.patch.dict(os.environ, {"COPILOT_HOOKS_STATE_DIR": str(self.state)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_merge(self, glab, ask: bool = False) -> tuple:
        args = SimpleNamespace(ref="demo#12", branch="feat/12-x", ask=ask, owner="me", project=None, plan_file=None)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = lite_merge.cmd_merge(args, glab)
        return code, out.getvalue()

    def plan(self) -> dict:
        return json.loads((self.state / "chief-plan.json").read_text(encoding="utf-8"))

    def test_queued_and_merged_are_read_back_from_gitlab(self) -> None:
        glab = fake_glab(0, "opened")
        code, out = self.run_merge(glab)
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("MERGE=queued mr=!7"), out)
        self.assertEqual(glab.calls[0], ["mr", "merge", "feat/12-x", "--repo", "me/demo", "--auto-merge", "--squash",
                                         "--remove-source-branch", "--yes"])
        self.assertTrue(self.run_merge(fake_glab(0, "merged"))[1].startswith("MERGE=merged"))

    def test_refusal_names_gitlabs_reason_and_asks_once(self) -> None:
        glab = fake_glab(1, "opened", stderr="\nERROR: pipeline failed\n")
        code, out = self.run_merge(glab, ask=True)
        self.assertEqual(code, 1)
        self.assertIn("MERGE=refused mr=!7", out)
        self.assertIn("reason=ERROR: pipeline failed", out)
        self.assertIn("MERGE_ASKED=merge-demo-12", out)
        self.run_merge(fake_glab(1, "opened", stderr="ERROR: pipeline failed"), ask=True)
        waiting = self.plan()["waiting_on_roberto"]
        self.assertEqual([w["id"] for w in waiting], ["merge-demo-12"])
        self.assertEqual(waiting[0]["ref"], "demo#12")
        self.assertIn("pipeline failed", waiting[0]["question"])
        kinds = [json.loads(line)["kind"] for line in
                 (self.state / "chief-journal.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(kinds, ["asked"])

    def test_a_boxed_glab_error_gives_its_message_not_the_banner(self) -> None:
        boxed = ("          \n   ERROR  \n          \n"
                 '  no open merge request available for "feat/12-x".      \n\n')
        code, out = self.run_merge(fake_glab(1, "closed", stderr=boxed), ask=True)
        self.assertEqual(code, 1)
        self.assertIn('reason=no open merge request available for "feat/12-x".\n', out)
        question = self.plan()["waiting_on_roberto"][0]["question"]
        self.assertTrue(question.endswith('available for "feat/12-x".'), question)

    def test_a_retry_lead_in_is_completed_with_gitlabs_merge_status(self) -> None:
        retry = ("   ERROR  \n\n  All attempts fail:\n"
                 "  #1: PUT https://gitlab.example/api/v4/projects/p/merge_requests/7/merge: 405 {message:\n"
                 "  405 Method Not Allowed}.\n")
        out = self.run_merge(fake_glab(1, "opened", stderr=retry, status="conflict"), ask=True)[1]
        self.assertIn("reason=All attempts fail (merge status: conflict)\n", out)
        self.assertIn("(merge status: conflict)", self.plan()["waiting_on_roberto"][0]["question"])

    def test_a_mergeable_status_adds_nothing(self) -> None:
        out = self.run_merge(fake_glab(1, "opened", stderr="ERROR: boom", status="mergeable"))[1]
        self.assertTrue(out.rstrip().endswith("reason=ERROR: boom"), out)

    def test_refusal_without_ask_writes_no_plan(self) -> None:
        self.assertIn("MERGE=refused", self.run_merge(fake_glab(1, "opened", stderr="conflict"))[1])
        self.assertFalse((self.state / "chief-plan.json").exists())

    def test_a_merge_gitlab_already_did_wins_over_a_nonzero_exit(self) -> None:
        self.assertTrue(self.run_merge(fake_glab(1, "merged"))[1].startswith("MERGE=merged"))

    def test_a_closed_request_is_refused(self) -> None:
        self.assertIn("reason=merge request is closed", self.run_merge(fake_glab(0, "closed"))[1])

    def test_unknowns(self) -> None:
        def missing(_args):
            raise FileNotFoundError
        self.assertEqual(self.run_merge(missing, ask=True), (1, "MERGE=unknown reason=glab not installed\n"))
        code, out = self.run_merge(fake_glab(0, "opened", view_rc=1), ask=True)
        self.assertEqual(code, 1)
        self.assertTrue(out.startswith("MERGE=unknown reason=glab mr view failed"), out)
        self.assertFalse((self.state / "chief-plan.json").exists())


if __name__ == "__main__":
    unittest.main()
