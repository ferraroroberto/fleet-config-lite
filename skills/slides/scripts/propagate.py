"""Re-stamp shared CSS/markup blocks from one slide into every slide of a deck.

The deck's shared zones are delimited by named anchors, in two styles:

    /* ==slides:tokens== */   ...   /* ==/slides:tokens== */        (inside <style>)
    <!-- ==slides:bootstrap== -->  ...  <!-- ==/slides:bootstrap== -->  (markup/scripts)

Workflow: edit a shared block ONCE in any slide file, then run

    python propagate.py <edited-slide.html> [deck-dir]

Every other ``*.html`` in the deck dir (``print.html`` excluded) gets the
same-named blocks replaced. The LLM never hand-edits ten files for a CSS
change; this script is the only sanctioned way to fan a shared change out.

Guarantees:
  * every block found in the source must exist exactly once in every target;
    a missing or duplicated anchor aborts the whole run with a loud, per-file
    error before a single byte is written (atomic: validate all, then write all);
  * stdlib only, by design (this repo keeps no virtualenv).
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

if sys.platform == "win32":  # emoji-safe output under piped/redirected capture
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("propagate")

# Two anchor styles: CSS comments (inside <style>) and HTML comments (markup).
BLOCK_STYLES = (
    re.compile(
        r"/\* ==slides:(?P<name>[\w-]+)== \*/.*?/\* ==/slides:(?P=name)== \*/",
        re.DOTALL,
    ),
    re.compile(
        r"<!-- ==slides:(?P<name>[\w-]+)== -->.*?<!-- ==/slides:(?P=name)== -->",
        re.DOTALL,
    ),
)


def extract_blocks(text: str, source_name: str) -> Dict[str, str]:
    """Return {block-name: full anchored text} for every shared block in *text*.

    Fails loudly on a duplicated block name: the source of truth must be
    unambiguous before anything is stamped anywhere.
    """
    blocks: Dict[str, str] = {}
    for pattern in BLOCK_STYLES:
        for m in pattern.finditer(text):
            name = m.group("name")
            if name in blocks:
                raise SystemExit(
                    f"❌ {source_name}: shared block '{name}' appears more than "
                    f"once; the source must define each block exactly once."
                )
            blocks[name] = m.group(0)
    return blocks


def stamp(text: str, blocks: Dict[str, str], target_name: str) -> str:
    """Replace every named block in *text* with the source's version.

    Every source block must match exactly once in the target; anything else
    means the deck's anchors have drifted, and silent partial propagation is
    exactly the failure this script exists to prevent.
    """
    for name, replacement in blocks.items():
        hits: List[re.Match] = []
        for pattern in BLOCK_STYLES:
            hits.extend(m for m in pattern.finditer(text) if m.group("name") == name)
        if len(hits) != 1:
            raise SystemExit(
                f"❌ {target_name}: shared block '{name}' matched {len(hits)} "
                f"time(s), expected exactly 1. Fix the anchors before propagating."
            )
        m = hits[0]
        text = text[: m.start()] + replacement + text[m.end() :]
    return text


def propagate(source: Path, deck_dir: Optional[Path] = None) -> int:
    """Stamp *source*'s shared blocks into every sibling slide file.

    Returns the number of files rewritten. Atomic: every target is validated
    and its new content computed before any file is written.
    """
    if not source.is_file():
        raise SystemExit(f"❌ source slide not found: {source}")
    deck = deck_dir or source.parent
    if not deck.is_dir():
        raise SystemExit(f"❌ deck dir not found: {deck}")

    blocks = extract_blocks(source.read_text(encoding="utf-8"), source.name)
    if not blocks:
        raise SystemExit(
            f"❌ {source.name}: no shared blocks found "
            f"(anchors look like '/* ==slides:name== */' or '<!-- ==slides:name== -->')."
        )
    log.info("ℹ️ source %s defines block(s): %s", source.name, ", ".join(sorted(blocks)))

    targets = sorted(
        p
        for p in deck.glob("*.html")
        if p.resolve() != source.resolve() and p.name != "print.html"
    )
    if not targets:
        log.info("ℹ️ no sibling slide files in %s; nothing to do.", deck)
        return 0

    # Validate-then-write: compute every new content first, only then touch disk.
    rewritten: List[tuple[Path, str]] = []
    for target in targets:
        new_text = stamp(target.read_text(encoding="utf-8"), blocks, target.name)
        rewritten.append((target, new_text))

    for target, new_text in rewritten:
        target.write_text(new_text, encoding="utf-8", newline="")
        log.info("✅ stamped %s", target.name)
    log.info("✅ propagated %d block(s) into %d file(s).", len(blocks), len(rewritten))
    return len(rewritten)


def main(argv: List[str]) -> int:
    if len(argv) < 2 or len(argv) > 3:
        log.error("usage: propagate.py <edited-slide.html> [deck-dir]")
        return 2
    source = Path(argv[1])
    deck = Path(argv[2]) if len(argv) == 3 else None
    propagate(source, deck)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
