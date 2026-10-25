"""The verification run's conventions-ratchet stage (stdlib unittest, no deps).

Run:  python -m unittest discover -s tests -v

`scripts/conventions_ratchet.py` exits 3 when it cannot measure the tree (a tracked .py
file that cannot be read or parsed), which
`test_structure_ratchet.assert_ratchet_passes` fails as NOT CONFIRMED.
"""

from __future__ import annotations

import tomllib
import unittest

from test_structure_ratchet import REPO_ROOT, assert_ratchet_passes

SCRIPT = REPO_ROOT / "scripts" / "conventions_ratchet.py"


class Declaration(unittest.TestCase):
    def test_ratchet_is_declared_and_its_script_is_vendored(self) -> None:
        fleet = tomllib.loads((REPO_ROOT / ".fleet.toml").read_text(encoding="utf-8"))
        table = fleet["conventions_ratchet"]
        self.assertIs(table["enabled"], True)
        self.assertTrue((REPO_ROOT / table["baseline"]).is_file())
        entry = fleet["vendored"]["conventions_ratchet"]
        self.assertEqual(entry["dest"], "scripts/conventions_ratchet.py")
        self.assertTrue((REPO_ROOT / entry["dest"]).is_file())

    def test_only_rules_with_a_matching_helper_are_enabled(self) -> None:
        fleet = tomllib.loads((REPO_ROOT / ".fleet.toml").read_text(encoding="utf-8"))
        table = fleet["conventions_ratchet"]
        # secret-compare and git-wrapper refuse to run without a declared helper, and
        # this repo has none.
        self.assertEqual(set(table["rules"]), {"no-window", "logging-not-print", "no-drive-path"})
        self.assertNotIn("secret_helpers", table)
        self.assertNotIn("git_wrappers", table)


class RealRepoRatchet(unittest.TestCase):
    def test_no_convention_count_rises_beyond_the_baseline(self) -> None:
        assert_ratchet_passes(self, SCRIPT)


if __name__ == "__main__":
    unittest.main()
