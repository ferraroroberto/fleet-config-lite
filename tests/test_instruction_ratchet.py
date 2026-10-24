"""The verification run's instruction-ratchet stage (stdlib unittest, no deps).

Run:  python -m unittest discover -s tests -v

`scripts/instruction_ratchet.py` exits 3 when it could not measure the tree (git
unusable, an unreadable file, an unclosed fence, an unreadable skill description):
nothing was checked. Only exit 0 passes here, so 3 fails as NOT CONFIRMED -- never a
pass, never a skip. The exit-code mapping is `test_structure_ratchet.run_ratchet` /
`passed`, shared because both stages are the same vendored-script contract.
"""

from __future__ import annotations

import tomllib
import unittest

from test_structure_ratchet import REPO_ROOT, passed, run_ratchet

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
        code, output = run_ratchet(SCRIPT)
        self.assertTrue(passed(code), f"exit {code}" + (" (NOT CONFIRMED)" if code == 3 else "") + f"\n{output}")


if __name__ == "__main__":
    unittest.main()
