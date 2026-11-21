"""The hooks-state folder has two resolvers, one per tier, and they must agree (stdlib unittest).

Run:  python -m unittest discover -s tests -v

The hooks tree cannot import `skills/_lib`, so `hooks/_lib.py` and
`skills/_lib/fleet_core/hooks_state.py` each resolve it. Nothing else may.
"""

from __future__ import annotations

import ast
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "hooks"))
sys.path.insert(0, str(REPO / "skills" / "_lib"))

import _lib as hooks_lib  # noqa: E402
import session_state  # noqa: E402
from chief import copilot_context  # noqa: E402
from fleet_core import hooks_state  # noqa: E402

RESOLVERS = ("hooks/_lib.py", "skills/_lib/fleet_core/hooks_state.py")


class AgreementTests(unittest.TestCase):
    def test_same_variable_name(self) -> None:
        self.assertEqual(hooks_lib.STATE_DIR_ENV_VAR, hooks_state.STATE_DIR_ENV_VAR)

    def test_same_folder_with_and_without_the_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {hooks_lib.STATE_DIR_ENV_VAR: tmp}):
                self.assertEqual(hooks_lib.state_dir(), hooks_state.state_dir())
                self.assertEqual(hooks_lib.state_dir(), Path(tmp))
                self.assertEqual(session_state.state_file().parent, Path(tmp))
        with mock.patch.dict(os.environ, clear=False):
            os.environ.pop(hooks_lib.STATE_DIR_ENV_VAR, None)
            self.assertEqual(hooks_lib.state_dir(), hooks_state.state_dir())

    def test_the_sessions_file_name_is_one_constant_across_tiers(self) -> None:
        self.assertEqual(copilot_context.SESSIONS_STATE_FILENAME, session_state.STATE_FILENAME)


class NoThirdResolverTests(unittest.TestCase):
    def test_only_the_two_resolvers_name_the_variable(self) -> None:
        offenders = []
        for folder in ("hooks", "skills", "scripts"):
            for path in sorted((REPO / folder).rglob("*.py")):
                rel = path.relative_to(REPO).as_posix()
                if rel in RESOLVERS:
                    continue
                for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                    if isinstance(node, ast.Constant) and node.value == hooks_lib.STATE_DIR_ENV_VAR:
                        offenders.append(rel)
        self.assertEqual(offenders, [], "resolve the state folder through hooks/_lib.state_dir() or fleet_core.hooks_state")


if __name__ == "__main__":
    unittest.main()
