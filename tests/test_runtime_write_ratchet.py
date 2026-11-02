"""The verification run's runtime-write-ratchet stage (stdlib unittest, no deps).

Run:  python -m unittest discover -s tests -v

`scripts/runtime_write_ratchet.py` exits 3 when it cannot establish a write target
(a new target it cannot resolve, or a tracked .py file it cannot parse), which
`test_structure_ratchet.assert_ratchet_passes` fails as NOT CONFIRMED.
"""

from __future__ import annotations

import tomllib
import unittest

from test_structure_ratchet import REPO_ROOT, assert_ratchet_passes

SCRIPT = REPO_ROOT / "scripts" / "runtime_write_ratchet.py"


class Declaration(unittest.TestCase):
    def test_ratchet_is_declared_and_both_scripts_are_vendored(self) -> None:
        fleet = tomllib.loads((REPO_ROOT / ".fleet.toml").read_text(encoding="utf-8"))
        table = fleet["runtime_write_ratchet"]
        self.assertIs(table["enabled"], True)
        self.assertTrue((REPO_ROOT / table["baseline"]).is_file())
        # The ratchet imports its sibling resolver, so both copies must be present.
        for name in ("runtime_write_ratchet", "runtime_write_resolve"):
            entry = fleet["vendored"][name]
            self.assertEqual(entry["dest"], f"scripts/{name}.py")
            self.assertTrue((REPO_ROOT / entry["dest"]).is_file())


class RealRepoRatchet(unittest.TestCase):
    def test_no_code_folder_write_rises_beyond_the_baseline(self) -> None:
        assert_ratchet_passes(self, SCRIPT)


if __name__ == "__main__":
    unittest.main()
