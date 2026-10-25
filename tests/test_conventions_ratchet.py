"""The verification run's conventions-ratchet stage (stdlib unittest, no deps).

Run:  python -m unittest discover -s tests -v

`scripts/conventions_ratchet.py` exits 3 when it could not measure the tree (git
unusable, a tracked .py file that cannot be read or parsed): nothing was checked.
Only exit 0 passes here, so 3 fails as NOT CONFIRMED -- never a pass, never a skip.
The exit-code mapping is `test_structure_ratchet.run_ratchet` / `passed`, shared
because both stages are the same vendored-script contract.
"""

from __future__ import annotations

import tomllib
import unittest

from test_structure_ratchet import REPO_ROOT, passed, run_ratchet

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
        code, output = run_ratchet(SCRIPT)
        self.assertTrue(passed(code), f"exit {code}" + (" (NOT CONFIRMED)" if code == 3 else "") + f"\n{output}")


if __name__ == "__main__":
    unittest.main()
