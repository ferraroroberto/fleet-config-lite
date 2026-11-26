"""The slides deck lint: catalog / local / ad-hoc classes, exit codes, inventory, session check.

Run:  python -m unittest discover -s tests -v

Each fixture deck is the placeholder example deck copied to a temp folder and
edited one way, so the content stays placeholder-only.
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
EXAMPLES = SLIDES / "assets" / "examples"
sys.path.insert(0, str(SLIDES / "scripts"))

import lint_deck  # noqa: E402

LOCAL_BLOCK = (
    "/* ==slides:local:wide-tiles== */\n"
    "/* purpose: tiles that span the full slide width · extends: tiles */\n"
    ".tiles.wide { grid-template-columns: repeat(4, 1fr); }\n"
    "/* ==/slides:local:wide-tiles== */\n"
)
ADHOC_RULE = ".callout { border-left: 4px solid var(--accent); padding: 12px; }\n"


class DeckFixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.deck = Path(self._tmp.name) / "deck"
        shutil.copytree(EXAMPLES, self.deck)

    def tearDown(self):
        self._tmp.cleanup()

    def edit(self, slide: str, old: str, new: str) -> None:
        path = self.deck / slide
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def add_css(self, slide: str, css: str) -> None:
        self.edit(slide, "</style>", css + "</style>")

    def lint(self):
        return lint_deck.lint_deck(self.deck)

    def findings(self):
        return [f for res in self.lint()[1] for f in res.findings]


class ClassesAndExitCodesTests(DeckFixture):
    def test_catalog_only_deck_is_final(self):
        self.assertEqual(self.lint()[0], lint_deck.EXIT_FINAL)
        self.assertEqual(lint_deck.main([str(self.deck)]), 0)

    def test_a_local_block_makes_the_deck_a_draft(self):
        self.add_css("s02-value.html", LOCAL_BLOCK)
        status, results, _ = self.lint()
        self.assertEqual(status, lint_deck.EXIT_DRAFT)
        self.assertEqual([r.local for r in results if r.local], [["wide-tiles"]])
        self.assertEqual(lint_deck.main([str(self.deck)]), 1)

    def test_an_adhoc_rule_is_a_finding(self):
        self.add_css("s02-value.html", LOCAL_BLOCK + ADHOC_RULE)
        self.assertEqual(self.lint()[0], lint_deck.EXIT_FINDINGS)
        self.assertIn("ad-hoc rule '.callout'", self.findings())
        self.assertEqual(lint_deck.main([str(self.deck)]), 2)

    def test_an_edited_catalog_block_names_the_component(self):
        self.edit("s01-rollout.html", "/* ==/slides:c:loopback@1== */", ".loopback { opacity: .5; }\n/* ==/slides:c:loopback@1== */")
        self.assertEqual(self.lint()[0], lint_deck.EXIT_FINDINGS)
        self.assertIn("catalog block 'loopback@1' (component 'loopback') was edited", self.findings())

    def test_an_unknown_catalog_version_is_a_finding(self):
        self.edit("s01-rollout.html", "==slides:c:loopback@1==", "==slides:c:loopback@9==")
        self.edit("s01-rollout.html", "==/slides:c:loopback@1==", "==/slides:c:loopback@9==")
        self.assertIn("catalog block 'loopback@9' is not in the catalog", self.findings())

    def test_a_local_block_without_its_purpose_is_a_finding(self):
        self.add_css("s02-value.html", LOCAL_BLOCK.replace("/* purpose: tiles that span the full slide width · extends: tiles */\n", ""))
        self.assertEqual(self.lint()[0], lint_deck.EXIT_FINDINGS)

    def test_a_local_block_extending_an_unknown_component_is_a_finding(self):
        self.add_css("s02-value.html", LOCAL_BLOCK.replace("extends: tiles", "extends: carousel"))
        self.assertIn("local block 'wide-tiles' extends unknown component 'carousel'", self.findings())

    def test_brand_values_may_change_but_other_tokens_may_not(self):
        self.edit("s01-rollout.html", "--brand: #1F7A54;", "--brand: #123456;")
        self.assertEqual(self.lint()[0], lint_deck.EXIT_FINAL)
        self.edit("s01-rollout.html", "--on-accent: #ffffff;", "--on-accent: #eeeeee;")
        self.assertIn("shared zone 'tokens' was edited beyond --brand/--brand-dark", self.findings())

    def test_an_edited_base_zone_is_a_finding(self):
        self.edit("s03-pilot.html", "/* ==/slides:base== */", "h1 { letter-spacing: 2px; }\n/* ==/slides:base== */")
        self.assertIn("shared zone 'base' was edited from the template's", self.findings())

    def test_style_attributes_may_only_set_knobs(self):
        self.edit("s02-value.html", "<body", '<body style="--cols: 3"')
        self.assertEqual(self.lint()[0], lint_deck.EXIT_FINAL)
        self.edit("s02-value.html", '<body style="--cols: 3"', '<body style="--cols: 3; color: red"')
        self.assertEqual(self.lint()[0], lint_deck.EXIT_FINDINGS)

    def test_could_not_check_is_exit_3(self):
        empty = Path(self._tmp.name) / "empty"
        empty.mkdir()
        self.assertEqual(lint_deck.main([str(empty)]), 3)
        self.assertEqual(lint_deck.main([str(Path(self._tmp.name) / "missing")]), 3)
        with mock.patch.object(lint_deck, "ASSETS", Path(self._tmp.name) / "no-assets"):
            self.assertEqual(lint_deck.main([str(self.deck)]), 3)


class InventoryTests(DeckFixture):
    def test_inventory_groups_unanchored_css_with_matches_and_candidates(self):
        # An unanchored copy of the figures block, a near cousin of the tiles, and a brand-new piece.
        self.edit("s03-pilot.html", "/* ==slides:c:figures@1== */", "")
        self.edit("s03-pilot.html", "/* ==/slides:c:figures@1== */", "")
        self.add_css("s02-value.html", ".tiles .tile-note { font-size: 14px; color: var(--muted); }\n" + ADHOC_RULE)
        self.assertEqual(lint_deck.main([str(self.deck), "--inventory"]), 2)
        report = (self.deck / lint_deck.REPORT_FILE).read_text(encoding="utf-8")
        self.assertIn("## Group 2: `.cap`, `.figure`, `.figures`, `.num`", report)  # joined by markup nesting
        self.assertIn("likely catalog match (`figures@1`", report)
        self.assertIn("near match: candidate variant (`tiles@1`", report)
        self.assertIn("## Group 1: `.callout`", report)
        self.assertIn("no match: candidate new component", report)
        self.assertIn("**Defined in:** s03-pilot.html", report)

    def test_inventory_refuses_a_tracked_deck_folder(self):
        with mock.patch.object(lint_deck, "_report_path_untracked", return_value=False):
            self.assertEqual(lint_deck.main([str(self.deck), "--inventory"]), 3)
        self.assertFalse((self.deck / lint_deck.REPORT_FILE).exists())


class SessionCheckTests(DeckFixture):
    def test_skill_assets_changing_during_a_session_fails(self):
        assets = Path(self._tmp.name) / "assets"
        shutil.copytree(SLIDES / "assets", assets)
        with mock.patch.object(lint_deck, "ASSETS", assets):
            self.assertEqual(lint_deck.main([str(self.deck), "--session-start"]), 0)
            self.assertEqual(lint_deck.main([str(self.deck)]), 0)
            (assets / "components.md").write_text("edited", encoding="utf-8")
            self.assertEqual(lint_deck.main([str(self.deck)]), 2)
            self.assertEqual(lint_deck.lint_deck(self.deck)[2], ["the skill's assets/ folder changed during this deck session"])

    def test_an_unreadable_session_record_is_exit_3(self):
        (self.deck / lint_deck.SESSION_FILE).write_text("not json", encoding="utf-8")
        self.assertEqual(lint_deck.main([str(self.deck)]), 3)


if __name__ == "__main__":
    unittest.main()
