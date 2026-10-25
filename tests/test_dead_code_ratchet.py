"""The verification run's dead-code-ratchet stage (stdlib unittest, no deps).

Run:  python -m unittest discover -s tests -v

`scripts/dead_code_ratchet.py` exits 3 when it cannot measure the tree (a tracked .py
file that cannot be read or parsed), which
`test_structure_ratchet.assert_ratchet_passes` fails as NOT CONFIRMED.
"""

from __future__ import annotations

import tomllib
import unittest

from test_structure_ratchet import REPO_ROOT, assert_ratchet_passes

SCRIPT = REPO_ROOT / "scripts" / "dead_code_ratchet.py"


class Declaration(unittest.TestCase):
    def test_ratchet_is_declared_and_its_script_is_vendored(self) -> None:
        fleet = tomllib.loads((REPO_ROOT / ".fleet.toml").read_text(encoding="utf-8"))
        self.assertIs(fleet["dead_code_ratchet"]["enabled"], True)
        self.assertTrue((REPO_ROOT / fleet["dead_code_ratchet"]["baseline"]).is_file())
        entry = fleet["vendored"]["dead_code_ratchet"]
        self.assertEqual(entry["dest"], "scripts/dead_code_ratchet.py")
        self.assertTrue((REPO_ROOT / entry["dest"]).is_file())


class RealRepoRatchet(unittest.TestCase):
    def test_no_unreferenced_definition_beyond_the_baseline(self) -> None:
        assert_ratchet_passes(self, SCRIPT)


if __name__ == "__main__":
    unittest.main()
