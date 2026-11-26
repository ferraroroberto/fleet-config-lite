"""Re-base a deck: local blocks become the catalog blocks of the same name, or nothing is written.

Run:  python -m unittest discover -s tests -v

Each test canonizes a request into a temp copy of the skill's assets, the way a
merged component request would, and re-bases a copy of the placeholder deck.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
SLIDES = REPO / "skills" / "slides"
sys.path.insert(0, str(SLIDES / "scripts"))

import build_catalog  # noqa: E402
import lint_deck  # noqa: E402
import rebase_deck  # noqa: E402

RULE = ".tiles.wide-tiles { grid-template-columns: repeat(2, 1fr); }\n"


def local(extends: str, name: str = "wide-tiles", rule: str = RULE) -> str:
    return (
        f"/* ==slides:local:{name}== */\n/* purpose: tiles on two wide columns · extends: {extends} */\n"
        f"{rule}/* ==/slides:local:{name}== */\n"
    )


class RebaseFixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.deck, self.assets = root / "deck", root / "assets"
        shutil.copytree(SLIDES / "assets" / "examples", self.deck)
        shutil.copytree(SLIDES / "assets", self.assets)
        patcher = mock.patch.object(lint_deck, "ASSETS", self.assets)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)
        self.slide = self.deck / "s02-value.html"

    def edit(self, old: str, new: str) -> None:
        text = self.slide.read_text(encoding="utf-8")
        self.assertIn(old, text)
        self.slide.write_text(text.replace(old, new, 1), encoding="utf-8")

    def add_local(self, block: str) -> None:
        self.edit('<div class="tiles">', '<div class="tiles wide-tiles">')
        self.edit("</style>", block + "</style>")

    def canonize(self, rule: str = RULE) -> None:
        """Add `tiles.wide-tiles` to the temp ledger and bump `tiles` to version 2."""
        md = (self.assets / "components.md").read_text(encoding="utf-8")
        head, entry = md.split("## 5. Value tiles", 1)
        entry, tail = entry.split("## 6. ", 1)
        entry = entry.replace("**version:** 1", "**version:** 2").replace("tiles@1==", "tiles@2==")
        entry = entry.replace("  - `tiles`:", "  - `tiles.wide-tiles`: two wide columns.\n  - `tiles`:")
        entry += f"```css\n/* ==slides:c:tiles.wide-tiles@2== */\n{rule}/* ==/slides:c:tiles.wide-tiles@2== */\n```\n\n"
        md = head + "## 5. Value tiles" + entry + "## 6. " + tail
        (self.assets / "components.md").write_text(md, encoding="utf-8")
        index = build_catalog.render(build_catalog.parse_catalog(md))
        (self.assets / "catalog.json").write_text(index, encoding="utf-8")

    def snapshot(self) -> dict:
        return {p.name: p.read_bytes() for p in self.deck.glob("*.html")}

    def assert_refused(self, needle: str) -> None:
        before = self.snapshot()
        written, problems = rebase_deck.rebase(self.deck)
        self.assertEqual(written, [])
        self.assertTrue(any(needle in p for p in problems), problems)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(rebase_deck.main([str(self.deck)]), 1)


class RebaseTests(RebaseFixture):
    def test_a_local_block_becomes_its_catalog_block_and_the_deck_is_final(self):
        self.add_local(local("tiles"))
        self.assertEqual(lint_deck.main([str(self.deck)]), 1)
        self.canonize()
        self.assertEqual(rebase_deck.main([str(self.deck)]), 0)
        text = self.slide.read_text(encoding="utf-8")
        self.assertNotIn("slides:local:", text)
        self.assertIn("/* ==slides:c:tiles@2== */", text)
        self.assertLess(text.index("slides:c:tiles@2=="), text.index("slides:c:tiles.wide-tiles@2=="))
        self.assertEqual(lint_deck.main([str(self.deck)]), 0)

    def test_a_variant_stays_after_its_base_block_and_brings_a_missing_one(self):
        self.canonize()
        self.add_local(local("tiles"))
        base = build_catalog.component_blocks(self.slide.read_text(encoding="utf-8"))[0][2]
        self.edit(base + "\n", "")
        self.assertEqual(rebase_deck.main([str(self.deck)]), 0)
        text = self.slide.read_text(encoding="utf-8")
        self.assertLess(text.index("slides:c:tiles@2=="), text.index("slides:c:tiles.wide-tiles@2=="))
        self.assertEqual(lint_deck.main([str(self.deck)]), 0)

    def test_a_local_block_above_its_base_block_moves_below_it(self):
        self.canonize()
        self.edit('<div class="tiles">', '<div class="tiles wide-tiles">')
        self.edit("/* ==slides:c:tiles@1== */", local("tiles") + "/* ==slides:c:tiles@1== */")
        self.assertEqual(rebase_deck.main([str(self.deck)]), 0)
        text = self.slide.read_text(encoding="utf-8")
        self.assertLess(text.index("slides:c:tiles@2=="), text.index("slides:c:tiles.wide-tiles@2=="))
        self.assertEqual(lint_deck.main([str(self.deck)]), 0)

    def test_crlf_slides_keep_their_line_endings(self):
        self.add_local(local("tiles"))
        self.slide.write_bytes(self.slide.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        self.canonize()
        self.assertEqual(rebase_deck.main([str(self.deck)]), 0)
        data = self.slide.read_bytes()
        self.assertEqual(data.count(b"\n"), data.count(b"\r\n"))
        self.assertEqual(lint_deck.main([str(self.deck)]), 0)


class RefusalTests(RebaseFixture):
    def test_a_missing_catalog_entry(self):
        self.add_local(local("tiles"))
        self.assert_refused("missing catalog entry 'tiles.wide-tiles'")

    def test_an_entry_that_extends_something_else(self):
        self.add_local(local("cases"))
        self.canonize()
        self.assert_refused("mismatched catalog entry")

    def test_an_entry_that_leaves_a_used_class_unstyled(self):
        self.add_local(local("tiles"))
        self.canonize(RULE.replace(".wide-tiles", ".tiles-wide"))
        self.assert_refused("does not style the class(es) wide-tiles")

    def test_an_older_catalog_block_that_differs_in_more_than_its_version(self):
        self.canonize()
        self.edit(".tile h3 {", ".tile h3 { opacity: .9;")
        self.assert_refused("differs from 'tiles@2'")

    def test_a_drifted_index_is_could_not_check(self):
        (self.assets / "catalog.json").write_text('{"components": []}', encoding="utf-8")
        self.assertEqual(rebase_deck.main([str(self.deck)]), 3)


if __name__ == "__main__":
    unittest.main()
