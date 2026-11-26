"""Generate ``assets/catalog.json`` from ``assets/components.md``.

    python build_catalog.py            # rewrite catalog.json from components.md
    python build_catalog.py --check    # exit 1 when catalog.json has drifted

``components.md`` is the ledger a person edits; ``catalog.json`` is its
machine-readable index (id, version, zone, and per variant the anchor, the
CSS block's sha256 and the classes it owns), so a deck check can tell a
verbatim catalog block from an edited one. The index is generated, never
hand-edited.

Each catalog entry is a ``## N. Title`` section carrying ``- **id:**``,
``- **Purpose:**``, ``- **Use when:**``, ``- **Don't use when:**`` and
``- **Variants:**`` lines, worked markup, and one anchored CSS block per
variant (``/* ==slides:c:<id>[.<variant>]@<version>== */ … /* ==/…== */``),
unless ``- **CSS:** base zone`` says its styles live in the shared base zone.
The ``## Chooser`` table must name every component. Anything missing or
inconsistent fails generation with the entry named.

Stdlib only, by design (this repo keeps no virtualenv).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

if sys.platform == "win32":  # emoji-safe output under piped/redirected capture
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("build_catalog")

ASSETS = Path(__file__).resolve().parents[1] / "assets"
COMPONENTS_MD = ASSETS / "components.md"
CATALOG_JSON = ASSETS / "catalog.json"

#: One anchored component block, anchors included; the name is ``<id>`` or ``<id>.<variant>``.
COMPONENT_BLOCK = re.compile(
    r"/\* ==slides:c:(?P<name>[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)?)@(?P<version>\d+)== \*/"
    r".*?"
    r"/\* ==/slides:c:(?P=name)@(?P=version)== \*/",
    re.DOTALL,
)

SECTION = re.compile(r"^## (?P<head>.+)$", re.MULTILINE)
ENTRY_HEAD = re.compile(r"^\d+\. (?P<title>.+)$")
ID_LINE = re.compile(r"^- \*\*id:\*\* `(?P<id>[a-z][a-z0-9-]*)` · \*\*version:\*\* (?P<version>\d+)$", re.MULTILINE)
FIELD_LINE = re.compile(r"^- \*\*(?P<key>[^*]+):\*\*(?: (?P<value>.+))?$", re.MULTILINE)
VARIANT_LINE = re.compile(r"^  - `(?P<name>[^`]+)`: (?P<desc>.+)$", re.MULTILINE)
FENCE = re.compile(r"^```(?P<lang>\w+)\n(?P<body>.*?)^```$", re.MULTILINE | re.DOTALL)
SELECTOR = re.compile(r"([^{}]+)\{")
CLASS_NAME = re.compile(r"\.(-?[_a-zA-Z][\w-]*)")
TABLE_ROW = re.compile(r"^\|(?P<cells>.+)\|$", re.MULTILINE)
BACKTICKED = re.compile(r"`([^`]+)`")

REQUIRED_FIELDS = ("Purpose", "Use when", "Don't use when", "Variants")
BASE_ZONE = "base zone"


class CatalogError(ValueError):
    """``components.md`` is missing something the ledger requires."""


def block_hash(block: str) -> str:
    """sha256 of an anchored block, anchors included, line endings normalised."""
    return hashlib.sha256(block.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def component_blocks(text: str) -> List[Tuple[str, int, str]]:
    """Every anchored component block in *text* as ``(name, version, block)``."""
    return [(m.group("name"), int(m.group("version")), m.group(0)) for m in COMPONENT_BLOCK.finditer(text)]


def owned_classes(block: str) -> List[str]:
    """Class names that appear in the block's selectors, sorted."""
    css = re.sub(r"/\*.*?\*/", "", block, flags=re.DOTALL)
    found = set()
    for selector in SELECTOR.findall(css):
        if selector.strip().startswith("@"):
            continue
        found.update(CLASS_NAME.findall(selector))
    return sorted(found)


def _sections(md: str) -> List[Tuple[str, str]]:
    heads = list(SECTION.finditer(md))
    return [
        (h.group("head").strip(), md[h.end() : heads[i + 1].start() if i + 1 < len(heads) else len(md)])
        for i, h in enumerate(heads)
    ]


def _parse_entry(title: str, body: str) -> Dict:
    id_m = ID_LINE.search(body)
    if not id_m:
        raise CatalogError(f"'{title}': missing the '- **id:** `<id>` · **version:** N' line")
    cid, version = id_m.group("id"), int(id_m.group("version"))
    fields = {m.group("key"): (m.group("value") or "").strip() for m in FIELD_LINE.finditer(body)}
    for key in REQUIRED_FIELDS:
        if key not in fields or (key != "Variants" and not fields[key]):
            raise CatalogError(f"'{cid}': missing '{key}'")
    variants = [(m.group("name"), m.group("desc").strip()) for m in VARIANT_LINE.finditer(body)]
    if not variants:
        raise CatalogError(f"'{cid}': lists no variants")
    for name, _ in variants:
        if name != cid and not name.startswith(cid + "."):
            raise CatalogError(f"'{cid}': variant '{name}' must be '{cid}' or '{cid}.<variant>'")
    fences = list(FENCE.finditer(body))
    if not any(f.group("lang") == "html" for f in fences):
        raise CatalogError(f"'{cid}': no worked HTML markup")

    zone = "base" if fields.get("CSS") == BASE_ZONE else "component"
    blocks: Dict[str, str] = {}
    for fence in (f for f in fences if f.group("lang") == "css"):
        for name, block_version, block in component_blocks(fence.group("body")):
            if name in blocks:
                raise CatalogError(f"'{cid}': block '{name}' is defined twice")
            if block_version != version:
                raise CatalogError(f"'{cid}': block '{name}' is at @{block_version}, the entry is at version {version}")
            blocks[name] = block
    names = [name for name, _ in variants]
    if zone == "base" and blocks:
        raise CatalogError(f"'{cid}': a base-zone component carries no component blocks")
    if zone == "component" and sorted(blocks) != sorted(names):
        raise CatalogError(f"'{cid}': variants {sorted(names)} and CSS blocks {sorted(blocks)} differ")

    return {
        "id": cid,
        "title": title,
        "version": version,
        "zone": zone,
        "variants": [
            {
                "name": name,
                "anchor": f"slides:c:{name}@{version}" if zone == "component" else None,
                "sha256": block_hash(blocks[name]) if zone == "component" else None,
                "classes": owned_classes(blocks[name]) if zone == "component" else [],
            }
            for name in names
        ],
    }


def _check_chooser(body: Optional[str], components: List[Dict]) -> None:
    if body is None:
        raise CatalogError("no '## Chooser' table")
    known = {c["id"]: {v["name"] for v in c["variants"]} for c in components}
    chosen = set()
    for row in TABLE_ROW.finditer(body):
        cells = [c.strip() for c in row.group("cells").split("|")]
        if len(cells) < 3 or set(cells[1]) <= set("-: "):
            continue
        ids = BACKTICKED.findall(cells[1])
        for cid in ids:
            if cid not in known:
                raise CatalogError(f"chooser names unknown component '{cid}'")
            for variant in BACKTICKED.findall(cells[2]):
                if variant.split(".")[0] == cid and variant not in known[cid]:
                    raise CatalogError(f"chooser names unknown variant '{variant}'")
        chosen.update(ids)
    missing = sorted(set(known) - chosen)
    if missing:
        raise CatalogError(f"chooser table does not cover: {', '.join(missing)}")


def parse_catalog(md: str) -> Dict:
    """The catalog index for *md*, or ``CatalogError`` naming what is wrong."""
    components: List[Dict] = []
    chooser: Optional[str] = None
    for head, body in _sections(md):
        if head == "Chooser":
            chooser = body
            continue
        entry = ENTRY_HEAD.match(head)
        if entry:
            components.append(_parse_entry(entry.group("title"), body))
    if not components:
        raise CatalogError("no '## N. Title' component entries")
    ids = [c["id"] for c in components]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise CatalogError(f"duplicate component id(s): {', '.join(duplicates)}")
    _check_chooser(chooser, components)
    return {"source": "components.md", "components": components}


def render(catalog: Dict) -> str:
    """The exact text ``catalog.json`` holds for *catalog*."""
    return json.dumps(catalog, indent=2, ensure_ascii=False) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate assets/catalog.json from assets/components.md.")
    parser.add_argument("--check", action="store_true", help="exit 1 when catalog.json differs from components.md")
    args = parser.parse_args(argv)
    try:
        expected = render(parse_catalog(COMPONENTS_MD.read_text(encoding="utf-8")))
    except CatalogError as exc:
        log.error("❌ components.md: %s", exc)
        return 1
    if args.check:
        current = CATALOG_JSON.read_text(encoding="utf-8") if CATALOG_JSON.is_file() else None
        if current is None or current.replace("\r\n", "\n") != expected:
            log.error("❌ catalog.json is out of date; run build_catalog.py to regenerate it.")
            return 1
        log.info("✅ catalog.json matches components.md.")
        return 0
    # runtime-write-exempt: regenerates the tracked catalog index, a source artifact beside its ledger
    CATALOG_JSON.write_text(expected, encoding="utf-8", newline="\n")
    log.info("✅ wrote %s", CATALOG_JSON.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
