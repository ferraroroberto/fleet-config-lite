"""The verification run's request-budget-ratchet stage (stdlib unittest, no deps).

Run:  python -m unittest discover -s tests -v

`scripts/request_budget_ratchet.py` exits 3 when it cannot measure the tree (git unusable, a
file that cannot be read or parsed), which
`test_structure_ratchet.assert_ratchet_passes` fails as NOT CONFIRMED.
"""

from __future__ import annotations

import tomllib
import unittest

from test_structure_ratchet import REPO_ROOT, assert_ratchet_passes

SCRIPT = REPO_ROOT / "scripts" / "request_budget_ratchet.py"


class Declaration(unittest.TestCase):
    def test_ratchet_is_declared_and_its_scripts_are_vendored(self) -> None:
        fleet = tomllib.loads((REPO_ROOT / ".fleet.toml").read_text(encoding="utf-8"))
        table = fleet["request_budget_ratchet"]
        self.assertIs(table["enabled"], True)
        self.assertTrue((REPO_ROOT / table["baseline"]).is_file())
        for name in ("request_budget_ratchet", "request_budget_scan", "ratchet_baseline"):
            entry = fleet["vendored"][name]
            self.assertEqual(entry["dest"], f"scripts/{name}.py")
            self.assertTrue((REPO_ROOT / entry["dest"]).is_file())


class RealRepoRatchet(unittest.TestCase):
    def test_no_request_budget_count_rises_beyond_the_baseline(self) -> None:
        assert_ratchet_passes(self, SCRIPT)


if __name__ == "__main__":
    unittest.main()
