"""Lint a deck for CSS that is not in the component catalog.

    python lint_deck.py <deck-dir>                   # classify every slide, exit with the deck status
    python lint_deck.py <deck-dir> --inventory       # also write lint-inventory.md beside the deck
    python lint_deck.py <deck-dir> --session-start   # record the skill's assets/ hash for this session

Every slide's CSS falls in one of three classes:

* **catalog** — a ``==slides:c:<id>…==`` block whose bytes hash-match
  ``assets/catalog.json``, plus the shared ``tokens`` and ``base`` zones
  (``base`` byte-equal to the template's, ``tokens`` differing only in the
  ``--brand``/``--brand-dark`` values). Passes.
* **local** — a ``==slides:local:<name>==`` block whose first comment is
  ``/* purpose: <one line> · extends: <catalog id|none> */``. Allowed while
  drafting.
* **ad-hoc** — any other CSS rule, a non-custom-property ``style``
  attribute, an edited or unknown catalog block, or a malformed local block.
  A finding.

Exit codes: 0 final (catalog only), 1 draft (local blocks, no ad-hoc),
2 findings (ad-hoc present, or the skill's assets/ changed since
``--session-start``), 3 could not check (no deck, no slides, unreadable
catalog or template). A check that could not run is never reported as clean.

``--inventory`` groups a deck's unanchored rules by the classes they style,
matches each group against the catalog by class names and declared
properties, and writes the report beside the deck; it refuses a deck folder
inside a git work tree unless the report path is ignored there, so client
material never lands in a tracked path.

Stdlib only, by design (this repo keeps no virtualenv); writes go through the
sibling ``skills/_lib`` guarded writer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_lib"))
from git_run import run_git  # noqa: E402
from runtime_files import save_text  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_catalog import COMPONENT_BLOCK, block_hash, component_blocks  # noqa: E402

if sys.platform == "win32":  # emoji-safe output under piped/redirected capture
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("lint_deck")

ASSETS = Path(__file__).resolve().parents[1] / "assets"
SESSION_FILE = ".slides-session.json"
REPORT_FILE = "lint-inventory.md"

EXIT_FINAL, EXIT_DRAFT, EXIT_FINDINGS, EXIT_UNKNOWN = 0, 1, 2, 3
STATUS = {EXIT_FINAL: "final", EXIT_DRAFT: "draft", EXIT_FINDINGS: "findings", EXIT_UNKNOWN: "could not check"}

STYLE_ELEMENT = re.compile(r"<style\b[^>]*>(?P<css>.*?)</style>", re.DOTALL | re.IGNORECASE)
SHARED_ZONE = re.compile(r"/\* ==slides:(?P<name>tokens|base)== \*/.*?/\* ==/slides:(?P=name)== \*/", re.DOTALL)
LOCAL_BLOCK = re.compile(
    r"/\* ==slides:local:(?P<name>[a-z][a-z0-9-]*)== \*/(?P<body>.*?)/\* ==/slides:local:(?P=name)== \*/",
    re.DOTALL,
)
LOCAL_META = re.compile(
    r"\A\s*/\*\s*purpose:\s*(?P<purpose>[^*\n]+?)\s*(?:·\s*extends:\s*(?P<extends>[a-z][a-z0-9-]*)\s*)?\*/"
)
STYLE_ATTR = re.compile(r"\sstyle\s*=\s*(?:\"(?P<dq>[^\"]*)\"|'(?P<sq>[^']*)')", re.IGNORECASE)
COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
BRAND_VALUE = re.compile(r"(--brand(?:-dark)?\s*:)[^;]*;")
CLASS_NAME = re.compile(r"\.(-?[_a-zA-Z][\w-]*)")
PROPERTY = re.compile(r"(?:^|;)\s*(?P<prop>-?[a-zA-Z][\w-]*)\s*:")

#: Inventory match thresholds on the combined score (0.7 × class overlap + 0.3 × property overlap):
#: class names carry the identity of a component, declared properties only its shape.
LIKELY_MATCH, NEAR_MATCH = 0.6, 0.25

VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class CheckError(RuntimeError):
    """The lint could not establish a result; reported as exit 3, never as clean."""


@dataclass
class Rule:
    slide: str
    selector: str
    declarations: str

    def classes(self) -> Set[str]:
        return set(CLASS_NAME.findall(self.selector))

    def properties(self) -> Set[str]:
        return {m.group("prop").lower() for m in PROPERTY.finditer(self.declarations)}


@dataclass
class SlideResult:
    name: str
    catalog: List[str] = field(default_factory=list)
    local: List[str] = field(default_factory=list)
    findings: List[str] = field(default_factory=list)
    adhoc_rules: List[Rule] = field(default_factory=list)
    classes_used: Set[str] = field(default_factory=set)
    nested_in: Dict[str, Set[str]] = field(default_factory=dict)


class ClassNesting(HTMLParser):
    """Every class used in the markup, and for each the classes of its ancestor elements."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: List[Tuple[str, Set[str]]] = []
        self.nested_in: Dict[str, Set[str]] = {}

    def _element(self, tag: str, attrs: List[Tuple[str, Optional[str]]], opens: bool) -> None:
        classes = set((dict(attrs).get("class") or "").split())
        ancestors = set().union(*(c for _, c in self.stack)) if self.stack else set()
        for c in classes:
            self.nested_in.setdefault(c, set()).update(ancestors)
        if opens:
            self.stack.append((tag, classes))

    def handle_starttag(self, tag, attrs):
        self._element(tag, attrs, opens=tag not in VOID_TAGS)

    def handle_startendtag(self, tag, attrs):
        self._element(tag, attrs, opens=False)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                return


def css_rules(css: str, slide: str) -> List[Rule]:
    """Leaf rules (and bare statements) of *css*, comments removed; nesting is flattened."""
    css = COMMENT.sub("", css)
    rules: List[Rule] = []
    stack: List[str] = []
    start = 0

    def statements(text: str) -> str:
        *done, rest = text.split(";")
        rules.extend(Rule(slide, s.strip(), "") for s in done if s.strip())
        return rest

    for i, ch in enumerate(css):
        if ch == "{":
            stack.append(statements(css[start:i]).strip())
            start = i + 1
        elif ch == "}":
            body = css[start:i]
            selector = stack.pop() if stack else "(unbalanced '}')"
            if body.strip() or not selector.startswith("@"):
                rules.append(Rule(slide, selector, body.strip()))
            start = i + 1
    tail = statements(css[start:]).strip()
    if tail or stack:
        rules.append(Rule(slide, tail or stack[-1], "(unterminated)"))
    return rules


def _normalised(zone: str, brand_free: bool = False) -> str:
    text = COMMENT.sub("", zone.replace("\r\n", "\n"))
    if brand_free:
        text = BRAND_VALUE.sub(r"\1 *;", text)
    return " ".join(text.split())


def load_reference() -> Tuple[Dict[str, Tuple[str, str]], Dict[str, str]]:
    """``({anchor: (sha256, component id)}, {zone: normalised template zone})`` or :class:`CheckError`."""
    try:
        catalog = json.loads((ASSETS / "catalog.json").read_text(encoding="utf-8"))
        anchors = {
            v["anchor"]: (v["sha256"], c["id"])
            for c in catalog["components"]
            for v in c["variants"]
            if v["anchor"]
        }
        template = (ASSETS / "template.html").read_text(encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise CheckError(f"cannot read the catalog or template under {ASSETS}: {exc}") from exc
    zones = {m.group("name"): m.group(0) for m in SHARED_ZONE.finditer(template)}
    if sorted(zones) != ["base", "tokens"]:
        raise CheckError("template.html lacks its tokens/base zones")
    return anchors, {"tokens": _normalised(zones["tokens"], True), "base": _normalised(zones["base"])}


def _check_shared(css: str, zones: Dict[str, str], result: SlideResult) -> str:
    found = {}
    for m in SHARED_ZONE.finditer(css):
        found.setdefault(m.group("name"), []).append(m.group(0))
    for name in ("tokens", "base"):
        hits = found.get(name, [])
        if len(hits) != 1:
            result.findings.append(f"shared zone '{name}' appears {len(hits)} time(s), expected 1")
            continue
        if _normalised(hits[0], brand_free=name == "tokens") != zones[name]:
            what = "beyond --brand/--brand-dark" if name == "tokens" else "from the template's"
            result.findings.append(f"shared zone '{name}' was edited {what}")
    return SHARED_ZONE.sub("", css)


def _check_catalog_blocks(css: str, anchors: Dict[str, Tuple[str, str]], result: SlideResult) -> str:
    for name, version, block in component_blocks(css):
        anchor = f"slides:c:{name}@{version}"
        if anchor not in anchors:
            result.findings.append(f"catalog block '{name}@{version}' is not in the catalog")
        elif block_hash(block) != anchors[anchor][0]:
            result.findings.append(f"catalog block '{name}@{version}' (component '{anchors[anchor][1]}') was edited")
        else:
            result.catalog.append(f"{name}@{version}")
    return COMPONENT_BLOCK.sub("", css)


def _check_local_blocks(css: str, component_ids: Set[str], result: SlideResult) -> str:
    for m in LOCAL_BLOCK.finditer(css):
        meta = LOCAL_META.match(m.group("body"))
        extends = meta and meta.group("extends")
        if not meta:
            result.findings.append(f"local block '{m.group('name')}' lacks its '/* purpose: … · extends: … */' line")
        elif extends and extends != "none" and extends not in component_ids:
            result.findings.append(f"local block '{m.group('name')}' extends unknown component '{extends}'")
        else:
            result.local.append(m.group("name"))
    return LOCAL_BLOCK.sub("", css)


def lint_slide(path: Path, anchors: Dict[str, Tuple[str, str]], zones: Dict[str, str]) -> SlideResult:
    try:
        html = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise CheckError(f"cannot read {path.name}: {exc}") from exc
    result = SlideResult(path.name)
    component_ids = {cid for _, cid in anchors.values()}
    css = "\n".join(m.group("css") for m in STYLE_ELEMENT.finditer(html))
    css = _check_shared(css, zones, result)
    css = _check_catalog_blocks(css, anchors, result)
    css = _check_local_blocks(css, component_ids, result)
    result.adhoc_rules = css_rules(css, path.name)
    for rule in result.adhoc_rules:
        result.findings.append(f"ad-hoc rule '{rule.selector}'")
    for m in STYLE_ATTR.finditer(html):
        decls = m.group("dq") if m.group("dq") is not None else m.group("sq")
        props = {p.strip().split(":")[0].strip() for p in decls.split(";") if p.strip()}
        if any(not p.startswith("--") for p in props):
            result.findings.append(f"style attribute sets more than knobs: '{decls.strip()}'")
    nesting = ClassNesting()
    nesting.feed(html)
    result.nested_in = nesting.nested_in
    result.classes_used = set(nesting.nested_in)
    return result


def deck_status(results: List[SlideResult]) -> int:
    if any(r.findings for r in results):
        return EXIT_FINDINGS
    return EXIT_DRAFT if any(r.local for r in results) else EXIT_FINAL


def assets_hash(assets: Optional[Path] = None) -> str:
    """sha256 over every file under the skill's assets/ folder, names included."""
    root = assets or ASSETS
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def session_finding(deck: Path) -> Optional[str]:
    """A finding when assets/ changed since ``--session-start``; None when unchanged or never recorded."""
    record = deck / SESSION_FILE
    if not record.exists():
        return None
    try:
        recorded = json.loads(record.read_text(encoding="utf-8"))["assets_sha256"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise CheckError(f"cannot read {SESSION_FILE}: {exc}") from exc
    if recorded != assets_hash():
        return "the skill's assets/ folder changed during this deck session"
    return None


def slide_files(deck: Path) -> List[Path]:
    if not deck.is_dir():
        raise CheckError(f"deck dir not found: {deck}")
    slides = sorted(p for p in deck.glob("*.html") if p.name != "print.html")
    if not slides:
        raise CheckError(f"no slide files (*.html) in {deck}")
    return slides


def lint_deck(deck: Path) -> Tuple[int, List[SlideResult], List[str]]:
    """``(exit code, per-slide results, deck-level findings)``; raises :class:`CheckError` when it cannot check."""
    anchors, zones = load_reference()
    results = [lint_slide(p, anchors, zones) for p in slide_files(deck)]
    deck_findings = [f for f in [session_finding(deck)] if f]
    status = EXIT_FINDINGS if deck_findings else deck_status(results)
    return status, results, deck_findings


# ---- inventory ---------------------------------------------------------------------------


def _catalog_shapes() -> Dict[str, Tuple[Set[str], Set[str]]]:
    """``{variant anchor: (classes, properties)}`` from the ledger's anchored blocks."""
    try:
        ledger = (ASSETS / "components.md").read_text(encoding="utf-8")
    except OSError as exc:
        raise CheckError(f"cannot read components.md: {exc}") from exc
    shapes = {}
    for name, version, block in component_blocks(ledger):
        rules = css_rules(block, "catalog")
        shapes[f"{name}@{version}"] = (
            set().union(*(r.classes() for r in rules)) if rules else set(),
            set().union(*(r.properties() for r in rules)) if rules else set(),
        )
    return shapes


def group_rules(rules: List[Rule], nested_in: Optional[Dict[str, Set[str]]] = None) -> List[Tuple[Set[str], List[Rule]]]:
    """Rules joined into groups whose selectors share a class, or whose classes nest in the markup.

    Union-find over class names: two classes join when one selector names both, or
    when an element carrying one sits inside an element carrying the other (a
    component's container and its parts). Class-less rules form one group.
    """
    parent: Dict[str, str] = {}

    def find(c: str) -> str:
        while parent.setdefault(c, c) != c:
            c = parent[c]
        return c

    for rule in rules:
        classes = sorted(rule.classes())
        for c in classes[1:]:
            parent[find(c)] = find(classes[0])
        if classes:
            find(classes[0])
    styled = set(parent)
    for c in styled:
        for ancestor in (nested_in or {}).get(c, set()) & styled:
            parent[find(ancestor)] = find(c)
    groups: Dict[str, Tuple[Set[str], List[Rule]]] = {}
    for rule in rules:
        classes = rule.classes()
        key = find(min(classes)) if classes else ""
        entry = groups.setdefault(key, (set(), []))
        entry[0].update(classes)
        entry[1].append(rule)
    return sorted(groups.values(), key=lambda g: (not g[0], sorted(g[0])))


def _jaccard(a: Set[str], b: Set[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def best_match(classes: Set[str], props: Set[str], shapes: Dict[str, Tuple[Set[str], Set[str]]]) -> Tuple[str, float, str]:
    """``(catalog variant, score, verdict)`` for one group of rules."""
    scored = [(0.7 * _jaccard(classes, c) + 0.3 * _jaccard(props, p), anchor) for anchor, (c, p) in shapes.items()]
    score, anchor = max(scored, default=(0.0, "—"))
    if score >= LIKELY_MATCH:
        return anchor, score, "likely catalog match"
    if score >= NEAR_MATCH:
        return anchor, score, "near match: candidate variant"
    return anchor, score, "no match: candidate new component"


def inventory_report(deck: Path, results: List[SlideResult]) -> str:
    shapes = _catalog_shapes()
    rules = [r for res in results for r in res.adhoc_rules]
    nested_in: Dict[str, Set[str]] = {}
    for res in results:
        for c, ancestors in res.nested_in.items():
            nested_in.setdefault(c, set()).update(ancestors)
    lines = [f"# Inventory: {deck.name}", "", f"{len(rules)} unanchored rule(s) across {len(results)} slide(s).", ""]
    for n, (classes, group) in enumerate(group_rules(rules, nested_in), 1):
        props = set().union(*(r.properties() for r in group))
        anchor, score, verdict = best_match(classes, props, shapes)
        defined_in = sorted({r.slide for r in group})
        used_by = sorted(res.name for res in results if res.classes_used & classes)
        lines += [
            f"## Group {n}: {', '.join(f'`.{c}`' for c in sorted(classes)) or '(no class selectors)'}",
            "",
            f"- **Verdict:** {verdict} (`{anchor}`, score {score:.2f})",
            f"- **Defined in:** {', '.join(defined_in)}",
            f"- **Used by:** {', '.join(used_by) or '—'}",
            f"- **Properties:** {', '.join(sorted(props)) or '—'}",
            "- **Rules:**",
            *(f"  - `{r.selector}` ({r.slide})" for r in group),
            "",
        ]
    other = [f"- {res.name}: {f}" for res in results for f in res.findings if not f.startswith("ad-hoc rule")]
    lines += ["## Other findings", "", *(other or ["- none"]), ""]
    return "\n".join(lines)


def report_path_untracked(report: Path) -> bool:
    """True only when *report* is outside any git work tree or ignored inside one."""
    deck = str(report.parent)
    try:
        inside = run_git(["-C", deck, "rev-parse", "--is-inside-work-tree"], timeout=30)
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            return True
        return run_git(["-C", deck, "check-ignore", "-q", report.name], timeout=30).returncode == 0
    except (OSError, ValueError) as exc:
        raise CheckError(f"cannot tell whether {deck} is tracked: {exc}") from exc


def write_inventory(deck: Path, results: List[SlideResult]) -> Path:
    report = deck / REPORT_FILE
    if not report_path_untracked(report):
        raise CheckError(f"{deck} is inside a git work tree; the inventory report never goes in a tracked path")
    save_text(report, inventory_report(deck, results), encoding="utf-8", newline="\n")
    return report


# ---- CLI ---------------------------------------------------------------------------------


def _print_results(status: int, results: List[SlideResult], deck_findings: List[str]) -> None:
    for res in results:
        kind = "ad-hoc" if res.findings else "local" if res.local else "catalog"
        log.info("%s %s: %s", "❌" if res.findings else "⚠️" if res.local else "✅", res.name, kind)
        for item in res.local:
            log.info("    local block '%s'", item)
        for item in res.findings:
            log.info("    %s", item)
    for item in deck_findings:
        log.info("❌ %s", item)
    log.info("deck status: %s (exit %d)", STATUS[status], status)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Lint a slide deck for CSS outside the component catalog.")
    parser.add_argument("deck", type=Path)
    parser.add_argument("--inventory", action="store_true", help=f"also write {REPORT_FILE} beside the deck")
    parser.add_argument("--session-start", action="store_true", help=f"record the skill's assets/ hash in {SESSION_FILE}")
    args = parser.parse_args(argv)
    try:
        if args.session_start:
            slide_files(args.deck)
            save_text(args.deck / SESSION_FILE, json.dumps({"assets_sha256": assets_hash()}) + "\n",
                      encoding="utf-8", newline="\n")
            log.info("✅ recorded the skill's assets/ hash in %s", SESSION_FILE)
            return EXIT_FINAL
        status, results, deck_findings = lint_deck(args.deck)
        _print_results(status, results, deck_findings)
        if args.inventory:
            log.info("✅ wrote %s", write_inventory(args.deck, results))
        return status
    except CheckError as exc:
        log.error("❌ could not check: %s", exc)
        log.info("deck status: %s (exit %d)", STATUS[EXIT_UNKNOWN], EXIT_UNKNOWN)
        return EXIT_UNKNOWN


if __name__ == "__main__":
    sys.exit(main())
