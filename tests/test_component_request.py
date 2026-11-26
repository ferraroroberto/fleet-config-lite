"""Component requests: one per local block, built from structure, never from the deck's words.

Run:  python -m unittest discover -s tests -v

Each fixture deck is the placeholder example deck copied to a temp folder, with
invented words and a figure added so a leak would be visible.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SLIDES = REPO / "skills" / "slides"
EXAMPLES = SLIDES / "assets" / "examples"
sys.path.insert(0, str(SLIDES / "scripts"))

import component_request  # noqa: E402

LOCAL_BLOCK = (
    "/* ==slides:local:wide-tiles== */\n"
    "/* purpose: tiles that span the full slide width · extends: tiles */\n"
    "/* Zorbex asked for this on slide two */\n"
    ".tiles.wide-tiles { grid-template-columns: repeat(2, 1fr); color: var(--accent); }\n"
    "/* ==/slides:local:wide-tiles== */\n"
)
NEW_BLOCK = (
    "/* ==slides:local:callout== */\n"
    "/* purpose: one boxed remark beside the content · extends: none */\n"
    ".callout { border-left: 4px solid var(--accent); padding: 1cqw; }\n"
    "/* ==/slides:local:callout== */\n"
)
SECRET_MARKUP = (
    '<div class="tiles wide-tiles" id="zorbex" data-client="Zorbex Orchard">\n'
    '    <div class="tile"><svg viewBox="0 0 24 24"><title>Zorbex</title></svg>\n'
    '      <h3 class="quibblet">Zorbex Orchard</h3><p title="Quibblet">Yield rose 47% at Vantablu</p>'
    '<img src="zorbex-logo.png" alt="Vantablu"></div>\n'
    "  </div>\n"
)
INVENTED = ("zorbex", "orchard", "vantablu", "quibblet", "47", "yield rose")


class _Texts(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.texts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        self.skip += tag in ("script", "style")

    def handle_endtag(self, tag):
        self.skip -= tag in ("script", "style")

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.texts.append(" ".join(data.split()))


class RequestFixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.deck = Path(self._tmp.name) / "deck"
        shutil.copytree(EXAMPLES, self.deck)
        self.slide = self.deck / "s02-value.html"
        self.edit('<div class="tiles">', SECRET_MARKUP + '  <div class="tiles">')
        self.edit("</style>", LOCAL_BLOCK + "</style>")

    def tearDown(self):
        self._tmp.cleanup()

    def edit(self, old: str, new: str) -> None:
        text = self.slide.read_text(encoding="utf-8")
        self.assertIn(old, text)
        self.slide.write_text(text.replace(old, new, 1), encoding="utf-8")

    def run_main(self, *args: str) -> int:
        return component_request.main([str(self.deck), *args])

    def request(self, name: str = "wide-tiles") -> str:
        return (self.deck / f"component-request-{name}.md").read_text(encoding="utf-8")

    def fill(self, use: str, dont: str) -> None:
        path = self.deck / "component-request-wide-tiles.md"
        text = self.request().replace("**Use when:** TODO", f"**Use when:** {use}")
        path.write_text(text.replace("**Don't use when:** TODO", f"**Don't use when:** {dont}"), encoding="utf-8")


class GenerationTests(RequestFixture):
    def test_one_request_per_local_block_with_its_kind_and_section(self):
        self.edit('<div class="band">', '<div class="callout">Zorbex</div>\n  <div class="band">')
        self.edit("</style>", NEW_BLOCK + "</style>")
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(
            sorted(p.name for p in self.deck.glob("component-request-*.md")),
            ["component-request-callout.md", "component-request-wide-tiles.md"],
        )
        self.assertIn("**Kind:** variant of `tiles`", self.request())
        self.assertIn("**Catalog section:** `tiles` (Value tiles)", self.request())
        self.assertIn("Keep the name `tiles.wide-tiles`", self.request())
        self.assertIn("**Kind:** new component", self.request("callout"))
        self.assertIn("**Catalog section:** new section `callout`", self.request("callout"))

    def test_a_request_holds_no_text_from_the_slide_copy(self):
        self.assertEqual(self.run_main(), 0)
        text = self.request()
        for invented in INVENTED:
            self.assertNotIn(invented, text.lower())
        shown = set()
        for slide in self.deck.glob("*.html"):
            parser = _Texts()
            parser.feed(slide.read_text(encoding="utf-8"))
            shown.update(t for t in parser.texts if len(t.split()) > 1)
        self.assertGreater(len(shown), 20)
        for copy in shown:
            self.assertNotIn(copy.lower(), text.lower())
        self.assertIn('<div class="tiles wide-tiles">', text)
        self.assertIn("Sample text", text)
        self.assertIn("<!-- icon paths -->", text)

    def test_copy_in_the_purpose_line_or_a_class_name_is_refused(self):
        self.edit("tiles that span the full slide width", "the Vantablu tiles")
        self.assertEqual(self.run_main(), 1)
        self.assertEqual(list(self.deck.glob("component-request-*.md")), [])

    def test_copy_hidden_in_an_id_selector_or_a_keyframes_name_is_refused(self):
        for css in ("#vantablu { padding: 1cqw; }", "@keyframes vantablu { to { opacity: 1; } }",
                    ".tiles { animation: vantablu 1s; }"):
            self.assertTrue(component_request.DeckCopy(self.deck, component_request.read_slides(self.deck), [])
                            .leaks(component_request.css_names(css)), css)

    def test_literal_colours_fonts_and_quoted_text_are_refused(self):
        for css in ("color: #123456;", "color: tomato;", "background: rgb(1, 2, 3);", "font-family: Acme;",
                    'content: "Hello";', "background: url(a.png);"):
            self.assertTrue(component_request.css_problems(f".x {{ {css} }}"), css)
        tokens = '.x[aria-expanded="true"] { color: var(--accent); white-space: nowrap; background: transparent; }'
        self.assertEqual(component_request.css_problems(tokens), [])

    def test_a_filled_request_is_kept_on_a_rerun(self):
        self.assertEqual(self.run_main(), 0)
        self.fill("the points need room", "there are more than two")
        before = self.request()
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(self.request(), before)

    def test_a_tracked_folder_is_refused_as_could_not_check(self):
        original = component_request.lint_deck.report_path_untracked
        component_request.lint_deck.report_path_untracked = lambda path: False
        try:
            self.assertEqual(self.run_main(), 3)
        finally:
            component_request.lint_deck.report_path_untracked = original
        self.assertEqual(list(self.deck.glob("component-request-*.md")), [])


class CheckTests(RequestFixture):
    def test_check_wants_the_todo_lines_filled(self):
        self.assertEqual(self.run_main("--check"), 1)  # not generated yet
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(self.run_main("--check"), 1)
        self.fill("the points need room", "there are more than two")
        self.assertEqual(self.run_main("--check"), 0)

    def test_check_refuses_deck_copy_written_into_a_filled_request(self):
        for leak in ("it suits Vantablu", "yield is 47 per site", "Drift shows up before plants do", "colour #1F7A54"):
            for old in self.deck.glob("component-request-*.md"):
                old.unlink()
            self.assertEqual(self.run_main(), 0)
            self.fill(leak, "there are more than two")
            self.assertEqual(self.run_main("--check"), 1, leak)

    def test_one_name_with_two_different_blocks_is_refused(self):
        other = self.deck / "s03-pilot.html"
        changed = LOCAL_BLOCK.replace("repeat(2, 1fr)", "repeat(3, 1fr)")
        other.write_text(other.read_text(encoding="utf-8").replace("</style>", changed + "</style>"), encoding="utf-8")
        self.assertEqual(self.run_main(), 1)


if __name__ == "__main__":
    unittest.main()
