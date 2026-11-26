"""Move a deck onto the current catalog: swap its local blocks for the blocks now in it.

    python rebase_deck.py <deck-dir>

A ``==slides:local:<name>==`` block is replaced by the catalog block of the same
name: ``<extends>.<name>`` when it extends a component (adding that component's
own block if the slide lacks it), else ``<name>``. A catalog block still at an
older version is re-stamped when only its version number changed.

The run is all or nothing. It refuses, writing no slide, when a local block has
no catalog entry, when the entry does not match (it extends something else, or
leaves a class the slide uses unstyled), or when an older catalog block differs
in more than its version. Run ``lint_deck.py`` afterwards: it is the gate.

Exit codes: 0 done, 1 refused (the reasons are listed), 3 could not check.
Stdlib only, by design; writes go through the sibling ``skills/_lib`` guarded writer.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_lib"))
from runtime_files import checked, save_text  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lint_deck  # noqa: E402
from build_catalog import COMPONENT_BLOCK, block_hash, component_blocks, owned_classes  # noqa: E402

log = logging.getLogger("rebase_deck")

EXIT_OK, EXIT_REFUSED, EXIT_UNKNOWN = 0, 1, 3
VERSION_MARK = re.compile(r"@\d+==")


class Entry(NamedTuple):
    name: str
    version: int
    block: str

    @property
    def base(self) -> str:
        """The component this variant belongs to (itself for a base variant)."""
        return self.name.split(".")[0]


def load_entries() -> Tuple[Dict[str, Entry], Set[str]]:
    """``({variant name: entry}, {base-zone class names})`` from a ledger that agrees with its index."""
    try:
        catalog = json.loads((lint_deck.ASSETS / "catalog.json").read_text(encoding="utf-8"))
        ledger = (lint_deck.ASSETS / "components.md").read_text(encoding="utf-8")
        template = (lint_deck.ASSETS / "template.html").read_text(encoding="utf-8")
        hashes = {v["anchor"]: v["sha256"] for c in catalog["components"] for v in c["variants"] if v["anchor"]}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise lint_deck.CheckError(f"cannot read the catalog under {lint_deck.ASSETS}: {exc}") from exc
    entries = {name: Entry(name, version, block) for name, version, block in component_blocks(ledger)}
    current = {f"slides:c:{e.name}@{e.version}": block_hash(e.block) for e in entries.values()}
    if current != hashes:
        raise lint_deck.CheckError("catalog.json and components.md differ; run build_catalog.py")
    zones = {c for m in lint_deck.SHARED_ZONE.finditer(template) for c in owned_classes(m.group(0))}
    return entries, zones


def restamp_old_blocks(html: str, entries: Dict[str, Entry], problems: List[str]) -> str:
    """Bring catalog blocks of an older version to the current one when nothing but the number differs."""

    def current(match: re.Match) -> str:
        name, version, block = match.group("name"), int(match.group("version")), match.group(0)
        entry = entries.get(name)
        if entry is None:
            problems.append(f"catalog block '{name}@{version}' is no longer in the catalog")
        elif entry.version != version:
            old = VERSION_MARK.sub("@==", block.replace("\r\n", "\n"))
            if old == VERSION_MARK.sub("@==", entry.block):
                return _with_newlines(entry.block, html)
            problems.append(
                f"catalog block '{name}@{version}' differs from '{name}@{entry.version}'; "
                "replace it with the block in components.md by hand"
            )
        return block

    return COMPONENT_BLOCK.sub(current, html)


def _with_newlines(block: str, html: str) -> str:
    return block.replace("\n", "\r\n") if "\r\n" in html else block


def entry_for(match: re.Match, entries: Dict[str, Entry]) -> Entry:
    """The catalog entry that replaces one local block, or :class:`ValueError` saying why none does."""
    name = match.group("name")
    meta = lint_deck.LOCAL_META.match(match.group("body"))
    if not meta:
        raise ValueError(f"local block '{name}' lacks its '/* purpose: … · extends: … */' line")
    extends = meta.group("extends")
    target = name if extends in (None, "none") else f"{extends}.{name}"
    if target in entries:
        return entries[target]
    others = sorted(v for v in entries if v == name or v.endswith(f".{name}"))
    if others:
        raise ValueError(
            f"mismatched catalog entry for local block '{name}': its line says '{target}', "
            f"the catalog has {', '.join(others)}"
        )
    raise ValueError(f"missing catalog entry '{target}' for local block '{name}'")


def swap_block(html: str, local_name: str, entry: Entry, entries: Dict[str, Entry]) -> str:
    """Replace one local block by *entry*, keeping a variant after its component's own block."""
    match = next(m for m in lint_deck.LOCAL_BLOCK.finditer(html) if m.group("name") == local_name)
    start, end = match.span()
    anchored = {name: block for name, _, block in component_blocks(html)}
    newline = "\r\n" if "\r\n" in html else "\n"
    base = entries.get(entry.base) if entry.base != entry.name else None
    pieces = [] if entry.name in anchored else [_with_newlines(entry.block, html)]
    if base and base.name not in anchored:
        pieces.insert(0, _with_newlines(base.block, html))
    insert = newline.join(pieces)
    base_end = html.find(anchored[base.name]) + len(anchored[base.name]) if base and base.name in anchored else -1
    if insert and base_end > start:
        return html[:start] + html[end:base_end] + newline + insert + html[base_end:]
    if not insert and html[end : end + len(newline)] == newline:
        end += len(newline)
    return html[:start] + insert + html[end:]


def rebase_slide(slide: str, html: str, entries: Dict[str, Entry], zones: Set[str], problems: List[str]) -> str:
    found: List[str] = []
    swaps: List[Tuple[str, Entry, Set[str]]] = []
    html = restamp_old_blocks(html, entries, found)
    for match in lint_deck.LOCAL_BLOCK.finditer(html):
        try:
            entry = entry_for(match, entries)
        except ValueError as exc:
            found.append(str(exc))
            continue
        rules = lint_deck.css_rules(match.group("body"), slide)
        swaps.append((match.group("name"), entry, set().union(*(r.classes() for r in rules))))
    nesting = lint_deck.ClassNesting()
    nesting.feed(html)
    used = set(nesting.nested_in)
    for name, entry, _ in swaps:
        html = swap_block(html, name, entry, entries)
    styled = zones | {c for _, _, block in component_blocks(html) for c in owned_classes(block)}
    for name, entry, classes in swaps:
        unstyled = sorted((classes & used) - styled)
        if unstyled:
            found.append(
                f"mismatched catalog entry '{entry.name}' for local block '{name}': "
                f"it does not style the class(es) {', '.join(unstyled)} the slide uses"
            )
        else:
            log.info("ℹ️ %s: local block '%s' → %s@%d", slide, name, entry.name, entry.version)
    problems += [f"{slide}: {p}" for p in found]
    return html


def rebase(deck: Path) -> Tuple[List[str], List[str]]:
    """``(rewritten slide names, problems)``; nothing is written when there is any problem."""
    entries, zones = load_entries()
    problems: List[str] = []
    pending: List[Tuple[Path, str]] = []
    for path in lint_deck.slide_files(deck):
        try:
            checked(path)
            with path.open(encoding="utf-8", newline="") as handle:
                html = handle.read()
        except (OSError, ValueError) as exc:
            raise lint_deck.CheckError(f"cannot rebase {path.name}: {exc}") from exc
        new = rebase_slide(path.name, html, entries, zones, problems)
        if new != html:
            pending.append((path, new))
    if problems:
        return [], problems
    for path, text in pending:
        save_text(path, text, encoding="utf-8", newline="")
    return [p.name for p, _ in pending], []


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Swap a deck's local blocks for the blocks now in the catalog.")
    parser.add_argument("deck", type=Path)
    args = parser.parse_args(argv)
    try:
        written, problems = rebase(args.deck)
    except lint_deck.CheckError as exc:
        log.error("❌ could not check: %s", exc)
        return EXIT_UNKNOWN
    if problems:
        log.error("❌ refused, no slide written:\n%s", "\n".join(problems))
        return EXIT_REFUSED
    if not written:
        log.info("ℹ️ nothing to rebase: no local block and no older catalog block")
    for name in written:
        log.info("✅ rewrote %s", name)
    log.info("ℹ️ now run lint_deck.py on the deck; it decides whether it is final")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
