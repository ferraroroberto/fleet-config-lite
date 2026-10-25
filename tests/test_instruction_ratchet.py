"""The verification run's instruction-ratchet stage (stdlib unittest, no deps).

Run:  python -m unittest discover -s tests -v

`scripts/instruction_ratchet.py` exits 3 when it cannot measure the tree (an unreadable
file, an unclosed fence, an unreadable skill description), which
`test_structure_ratchet.assert_ratchet_passes` fails as NOT CONFIRMED.
"""

from __future__ import annotations

import tomllib
import unittest

from test_structure_ratchet import REPO_ROOT, assert_ratchet_passes

SCRIPT = REPO_ROOT / "scripts" / "instruction_ratchet.py"


class Declaration(unittest.TestCase):
    def test_ratchet_is_declared_and_its_script_is_vendored(self) -> None:
        fleet = tomllib.loads((REPO_ROOT / ".fleet.toml").read_text(encoding="utf-8"))
        self.assertIs(fleet["instruction_ratchet"]["enabled"], True)
        self.assertTrue((REPO_ROOT / fleet["instruction_ratchet"]["baseline"]).is_file())
        entry = fleet["vendored"]["instruction_ratchet"]
        self.assertEqual(entry["dest"], "scripts/instruction_ratchet.py")
        self.assertTrue((REPO_ROOT / entry["dest"]).is_file())


class RealRepoRatchet(unittest.TestCase):
    def test_no_instruction_file_rises_above_its_baseline(self) -> None:
        assert_ratchet_passes(self, SCRIPT)


if __name__ == "__main__":
    unittest.main()
