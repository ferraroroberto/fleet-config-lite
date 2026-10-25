"""The verification run's doc-refs-ratchet stage (stdlib unittest, no deps).

Run:  python -m unittest discover -s tests -v

`scripts/doc_refs_ratchet.py` exits 3 when it cannot measure the tree (a file that is
not UTF-8, an unclosed fence or HTML comment), which
`test_structure_ratchet.assert_ratchet_passes` fails as NOT CONFIRMED.
"""

from __future__ import annotations

import tomllib
import unittest

from test_structure_ratchet import REPO_ROOT, assert_ratchet_passes

SCRIPT = REPO_ROOT / "scripts" / "doc_refs_ratchet.py"


class Declaration(unittest.TestCase):
    def test_ratchet_is_declared_and_its_script_is_vendored(self) -> None:
        fleet = tomllib.loads((REPO_ROOT / ".fleet.toml").read_text(encoding="utf-8"))
        self.assertIs(fleet["doc_refs_ratchet"]["enabled"], True)
        self.assertTrue((REPO_ROOT / fleet["doc_refs_ratchet"]["baseline"]).is_file())
        entry = fleet["vendored"]["doc_refs_ratchet"]
        self.assertEqual(entry["dest"], "scripts/doc_refs_ratchet.py")
        self.assertTrue((REPO_ROOT / entry["dest"]).is_file())


class RealRepoRatchet(unittest.TestCase):
    def test_no_dangling_doc_reference_beyond_the_baseline(self) -> None:
        assert_ratchet_passes(self, SCRIPT)


if __name__ == "__main__":
    unittest.main()
