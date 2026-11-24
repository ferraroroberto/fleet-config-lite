"""The verification run's clean-tree-ratchet stage (stdlib unittest, no deps).

Run:  python -m unittest discover -s tests -v

`scripts/clean_tree_ratchet.py` runs the declared install smoke once against a scratch
profile and exits 3 when it could not (git unusable, the smoke failed to start, timed out
or exited non-zero), which `test_structure_ratchet.assert_ratchet_passes` fails as
NOT CONFIRMED -- never a pass, never a skip. The smoke is Windows PowerShell running
`install.ps1`, so this stage is a Windows one, like the installer.
"""

from __future__ import annotations

import tomllib
import unittest

from test_structure_ratchet import REPO_ROOT, assert_ratchet_passes

SCRIPT = REPO_ROOT / "scripts" / "clean_tree_ratchet.py"
DEFAULT_BASELINE = ".ratchets/clean-tree.json"


class Declaration(unittest.TestCase):
    def test_ratchet_is_declared_and_its_scripts_are_vendored(self) -> None:
        fleet = tomllib.loads((REPO_ROOT / ".fleet.toml").read_text(encoding="utf-8"))
        table = fleet["clean_tree_ratchet"]
        self.assertIs(table["enabled"], True)
        self.assertTrue((REPO_ROOT / table.get("baseline", DEFAULT_BASELINE)).is_file())
        for name in ("clean_tree_ratchet", "ratchet_baseline"):
            entry = fleet["vendored"][name]
            self.assertEqual(entry["dest"], f"scripts/{name}.py")
            self.assertTrue((REPO_ROOT / entry["dest"]).is_file())

    def test_the_smoke_installs_into_the_scratch_profile_only(self) -> None:
        table = tomllib.loads((REPO_ROOT / ".fleet.toml").read_text(encoding="utf-8"))["clean_tree_ratchet"]
        self.assertEqual(table["data_dir_env"], "COPILOT_HOME")
        command = table["smoke"][-1]
        self.assertIn("$env:USERPROFILE = $env:COPILOT_HOME", command)
        self.assertIn("install.ps1", command)


class RealRepoRatchet(unittest.TestCase):
    def test_the_install_smoke_leaves_the_work_tree_unchanged(self) -> None:
        assert_ratchet_passes(self, SCRIPT)


if __name__ == "__main__":
    unittest.main()
