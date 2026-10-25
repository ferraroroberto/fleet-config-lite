"""The verification run's comment-ratchet stage (stdlib unittest, no deps).

Run:  python -m unittest discover -s tests -v

`scripts/comment_ratchet.py` exits 3 when it cannot measure the tree (git unusable, a file
that cannot be scanned), which
`test_structure_ratchet.assert_ratchet_passes` fails as NOT CONFIRMED.
"""

from __future__ import annotations

import tomllib
import unittest

from test_structure_ratchet import REPO_ROOT, assert_ratchet_passes

SCRIPT = REPO_ROOT / "scripts" / "comment_ratchet.py"


class Declaration(unittest.TestCase):
    def test_ratchet_is_declared_and_its_script_is_vendored(self) -> None:
        fleet = tomllib.loads((REPO_ROOT / ".fleet.toml").read_text(encoding="utf-8"))
        self.assertIs(fleet["comment_ratchet"]["enabled"], True)
        self.assertTrue((REPO_ROOT / fleet["comment_ratchet"]["baseline"]).is_file())
        entry = fleet["vendored"]["comment_ratchet"]
        self.assertEqual(entry["dest"], "scripts/comment_ratchet.py")
        self.assertTrue((REPO_ROOT / entry["dest"]).is_file())


class RealRepoRatchet(unittest.TestCase):
    def test_no_issue_reference_in_a_code_comment_beyond_the_baseline(self) -> None:
        assert_ratchet_passes(self, SCRIPT)


if __name__ == "__main__":
    unittest.main()
