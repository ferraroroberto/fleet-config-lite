"""The verification run's port-host-ratchet stage (stdlib unittest, no deps).

Run:  python -m unittest discover -s tests -v

`scripts/port_host_ratchet.py` exits 3 when it cannot measure the tree (git unusable, a file
that cannot be read or parsed), which
`test_structure_ratchet.assert_ratchet_passes` fails as NOT CONFIRMED.
"""

from __future__ import annotations

import tomllib
import unittest

from test_structure_ratchet import REPO_ROOT, assert_ratchet_passes

SCRIPT = REPO_ROOT / "scripts" / "port_host_ratchet.py"
DEFAULT_BASELINE = ".ratchets/port-host.json"


class Declaration(unittest.TestCase):
    def test_ratchet_is_declared_and_its_scripts_are_vendored(self) -> None:
        fleet = tomllib.loads((REPO_ROOT / ".fleet.toml").read_text(encoding="utf-8"))
        table = fleet["port_host_ratchet"]
        self.assertIs(table["enabled"], True)
        self.assertTrue((REPO_ROOT / table.get("baseline", DEFAULT_BASELINE)).is_file())
        for name in ("port_host_ratchet", "ratchet_baseline"):
            entry = fleet["vendored"][name]
            self.assertEqual(entry["dest"], f"scripts/{name}.py")
            self.assertTrue((REPO_ROOT / entry["dest"]).is_file())

    def test_every_declared_resolver_exists(self) -> None:
        fleet = tomllib.loads((REPO_ROOT / ".fleet.toml").read_text(encoding="utf-8"))
        for resolver in fleet["port_host_ratchet"].get("resolvers", []):
            self.assertTrue((REPO_ROOT / resolver).is_file(), resolver)


class RealRepoRatchet(unittest.TestCase):
    def test_no_port_or_host_literal_beyond_the_baseline(self) -> None:
        assert_ratchet_passes(self, SCRIPT)


if __name__ == "__main__":
    unittest.main()
