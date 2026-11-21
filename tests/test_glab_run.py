"""Tests for skills/_lib/glab_run.py (stdlib unittest, no network).

Run:  python -m unittest discover -s tests -v

The ladder every forge read shares, and the check that nothing else spawns glab.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skills" / "_lib"))

import glab_run  # noqa: E402


def _done(stdout: str = "", returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr)


def _raises(exc: BaseException):
    def run(_args):
        raise exc
    return run


class LadderTests(unittest.TestCase):
    def test_missing_glab_is_its_own_error(self) -> None:
        with self.assertRaisesRegex(glab_run.GlabError, "glab not installed"):
            glab_run.glab_json(["mr", "list"], _raises(FileNotFoundError()))

    def test_a_timeout_names_the_budget(self) -> None:
        with self.assertRaisesRegex(glab_run.GlabError, r"timed out after 5s"):
            glab_run.glab_text(["mr", "list"], _raises(subprocess.TimeoutExpired("glab", 5)))

    def test_a_failure_carries_glabs_message_not_its_banner(self) -> None:
        run = lambda _a: _done(returncode=1, stderr="\nERROR\n401 Unauthorized\n")  # noqa: E731
        with self.assertRaisesRegex(glab_run.GlabError, r"glab mr list failed: 401 Unauthorized"):
            glab_run.glab_text(["mr", "list"], run)

    def test_blank_and_garbled_output_are_unparseable_not_empty(self) -> None:
        for body in ("", "not json"):
            with self.subTest(body=body), self.assertRaisesRegex(glab_run.GlabError, "unparseable"):
                glab_run.glab_json(["mr", "list"], lambda _a, b=body: _done(b))

    def test_a_wrong_shape_is_refused(self) -> None:
        with self.assertRaisesRegex(glab_run.GlabError, "not a list"):
            glab_run.glab_json(["mr", "list"], lambda _a: _done("{}"), expect=list)
        with self.assertRaisesRegex(glab_run.GlabError, "not an object"):
            glab_run.glab_json(["mr", "view"], lambda _a: _done("[]"), expect=dict)

    def test_merge_requests_asks_for_every_state_and_keeps_rows(self) -> None:
        seen = []

        def run(args):
            seen.append(args)
            return _done('[{"iid": 1, "state": "merged"}, 3]')

        rows = glab_run.merge_requests("g/p", "feat/1-x", run)
        self.assertEqual(rows, [{"iid": 1, "state": "merged"}])
        self.assertEqual(seen[0], ["mr", "list", "--repo", "g/p", "--source-branch", "feat/1-x", "--all",
                                   "--output", "json"])

    def test_the_exit_status_stays_the_callers_on_glab_output(self) -> None:
        self.assertEqual(glab_run.glab_output(["mr", "merge"], lambda _a: _done(returncode=1)).returncode, 1)


def _spawns_glab(tree: ast.AST) -> bool:
    """True when a call passes an argv list whose first element is the literal "glab"."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for arg in node.args[:1]:
                if (isinstance(arg, (ast.List, ast.Tuple)) and arg.elts
                        and isinstance(arg.elts[0], ast.Constant) and arg.elts[0].value == "glab"):
                    return True
    return False


class SingleSpawnerTests(unittest.TestCase):
    def test_only_glab_run_spawns_glab(self) -> None:
        offenders = []
        for folder in ("skills", "hooks", "scripts"):
            for path in sorted((REPO / folder).rglob("*.py")):
                if path.name == "glab_run.py":
                    continue
                if _spawns_glab(ast.parse(path.read_text(encoding="utf-8"))):
                    offenders.append(path.relative_to(REPO).as_posix())
        self.assertEqual(offenders, [], "spawn glab through skills/_lib/glab_run.py, not a second copy of its ladder")


if __name__ == "__main__":
    unittest.main()
