"""The slides component catalog: ledger completeness, index drift, anchored examples.

Run:  python -m unittest discover -s tests -v
"""

from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
SLIDES = REPO / "skills" / "slides"
sys.path.insert(0, str(SLIDES / "scripts"))

import build_catalog  # noqa: E402
import propagate  # noqa: E402

COMPONENTS_MD = SLIDES / "assets" / "components.md"
PER_SLIDE_ZONE = re.compile(r"/\* ==/slides:base== \*/(?P<zone>.*?)</style>", re.DOTALL)
COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def ledger() -> str:
    return COMPONENTS_MD.read_text(encoding="utf-8")


def catalog_hashes() -> dict:
    catalog = build_catalog.parse_catalog(ledger())
    return {v["anchor"]: v["sha256"] for c in catalog["components"] for v in c["variants"] if v["anchor"]}


class CatalogIndexTests(unittest.TestCase):
    def test_catalog_json_matches_the_ledger(self):
        self.assertEqual(build_catalog.main(["--check"]), 0, "run skills/slides/scripts/build_catalog.py")

    def test_check_fails_when_the_index_drifts(self):
        with tempfile.TemporaryDirectory() as tmp:
            stale = Path(tmp) / "catalog.json"
            stale.write_text(build_catalog.CATALOG_JSON.read_text(encoding="utf-8").replace('"version": 1', '"version": 2', 1), encoding="utf-8")
            with mock.patch.object(build_catalog, "CATALOG_JSON", stale):
                self.assertEqual(build_catalog.main(["--check"]), 1)

    def test_check_fails_when_a_block_changes_in_the_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            edited = Path(tmp) / "components.md"
            edited.write_text(ledger().replace(".band { background: var(--soft);", ".band { background: var(--line);", 1), encoding="utf-8")
            with mock.patch.object(build_catalog, "COMPONENTS_MD", edited):
                self.assertEqual(build_catalog.main(["--check"]), 1)

    def test_every_component_carries_the_ledger_fields(self):
        components = build_catalog.parse_catalog(ledger())["components"]
        self.assertGreaterEqual(len(components), 14)
        for c in components:
            self.assertTrue(c["variants"], c["id"])
            if c["zone"] == "component":
                for v in c["variants"]:
                    self.assertEqual(v["anchor"], f"slides:c:{v['name']}@{c['version']}")
                    self.assertTrue(v["classes"], v["name"])


class LedgerValidationTests(unittest.TestCase):
    def assert_rejected(self, md: str, needle: str) -> None:
        with self.assertRaises(build_catalog.CatalogError) as ctx:
            build_catalog.parse_catalog(md)
        self.assertIn(needle, str(ctx.exception))

    def test_missing_use_when_names_the_component(self):
        md = re.sub(r"^- \*\*Use when:\*\* .*\n", "", ledger(), count=1, flags=re.MULTILINE)
        self.assert_rejected(md, "'header': missing 'Use when'")

    def test_a_component_missing_from_the_chooser_fails(self):
        md = re.sub(r"^\| .* \| `loopback` \| .*\n", "", ledger(), count=1, flags=re.MULTILINE)
        self.assert_rejected(md, "does not cover: loopback")

    def test_a_variant_without_its_block_fails(self):
        md = ledger().replace("  - `band`: same internal padding", "  - `band.wide`: a variant with no block\n  - `band`: same internal padding", 1)
        self.assert_rejected(md, "'band': variants")

    def test_a_block_at_another_version_fails(self):
        md = ledger().replace("/* ==slides:c:band@1== */", "/* ==slides:c:band@2== */", 1).replace(
            "/* ==/slides:c:band@1== */", "/* ==/slides:c:band@2== */", 1
        )
        self.assert_rejected(md, "'band': block 'band' is at @2")


class AnchoredSlidesTests(unittest.TestCase):
    def slide_files(self):
        return sorted((SLIDES / "assets" / "examples").glob("*.html")) + [SLIDES / "assets" / "template.html"]

    def test_per_slide_css_is_only_verbatim_catalog_blocks(self):
        hashes = catalog_hashes()
        for path in self.slide_files():
            zone = PER_SLIDE_ZONE.search(path.read_text(encoding="utf-8")).group("zone")
            for name, version, block in build_catalog.component_blocks(zone):
                anchor = f"slides:c:{name}@{version}"
                self.assertIn(anchor, hashes, f"{path.name}: {anchor} is not in the catalog")
                self.assertEqual(build_catalog.block_hash(block), hashes[anchor], f"{path.name}: {anchor} was edited")
            rest = COMMENT.sub("", build_catalog.COMPONENT_BLOCK.sub("", zone))
            self.assertEqual(rest.strip(), "", f"{path.name}: CSS outside a catalog block")

    def test_every_example_declares_its_components(self):
        for path in (SLIDES / "assets" / "examples").glob("*.html"):
            self.assertTrue(build_catalog.component_blocks(path.read_text(encoding="utf-8")), path.name)

    def test_propagate_leaves_component_blocks_alone(self):
        text = (SLIDES / "assets" / "examples" / "s01-rollout.html").read_text(encoding="utf-8")
        shared = propagate.extract_blocks(text, "s01-rollout.html")
        self.assertEqual(sorted(shared), ["base", "bootstrap", "toggle", "toggle-script", "tokens"])


if __name__ == "__main__":
    unittest.main()
