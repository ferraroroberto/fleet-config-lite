"""Write one component request per deck-local block, and check it carries nothing private.

    python component_request.py <deck-dir>            # write component-request-<name>.md per local block
    python component_request.py <deck-dir> --check    # check the filled requests before filing them

A request is meant to be filed in a public repository, so it is built from the
slide's structure, never from its words: sample markup keeps tags and known
class names only, every text becomes ``Sample text``, and the CSS must stand on
the design tokens (no literal colour, font, image or quoted text). Both modes
refuse a request that holds a word or figure of the deck's slide copy. A word
the skill's own documentation already uses is generic and allowed, so the check
is a screen: the owner still reads the request before filing it.

A request that already exists is kept, so a filled one is never overwritten;
delete it to regenerate. Requests are written beside the deck and refused inside
a tracked folder.

Exit codes: 0 done, 1 refused or incomplete (the reasons are listed),
3 could not check. Stdlib only, by design.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from string import Template
from typing import Dict, Iterable, List, NamedTuple, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_lib"))
from runtime_files import save_text  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lint_deck  # noqa: E402
from build_catalog import owned_classes, parse_catalog  # noqa: E402

log = logging.getLogger("component_request")

TEMPLATE_FILE = "component-request.md"
REQUEST_PREFIX = "component-request-"
SAMPLE = "Sample text"
EXIT_OK, EXIT_REFUSED, EXIT_UNKNOWN = 0, 1, 3

#: A run of this many words shared with the slide copy is copied text, even when each word is generic.
PHRASE_WORDS = 4

WORD = re.compile(r"[^\W\d_]{2,}")
FIGURE = re.compile(r"\d+(?:[.,]\d+)*")
FENCED = re.compile(r"^```(?P<lang>\w*)\n(?P<body>.*?)^```$", re.MULTILINE | re.DOTALL)
QUOTED = re.compile(r"\"([^\"\n]*)\"|'([^'\n]*)'")
CUSTOM_PROPERTY = re.compile(r"--([a-zA-Z][\w-]*)")
AT_PRELUDE = re.compile(r"@[\w-]+([^{};]*)")
#: Properties whose value is an identifier the author invents, so it can carry a name.
NAMING_PROPERTIES = {
    "animation", "animation-name", "container", "container-name", "counter-increment", "counter-reset", "grid-area",
}
HEX_COLOUR = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b")
COLOUR_FUNCTION = re.compile(r"\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch)\(\s*(?!from\s+var\()", re.IGNORECASE)
NAMED_COLOUR = re.compile(
    r"(?<![\w-])(?:aliceblue|antiquewhite|aqua|aquamarine|azure|beige|bisque|black|blanchedalmond|blue|"
    r"blueviolet|brown|burlywood|cadetblue|chartreuse|chocolate|coral|cornflowerblue|cornsilk|crimson|cyan|"
    r"darkblue|darkcyan|darkgoldenrod|darkgray|darkgreen|darkgrey|darkkhaki|darkmagenta|darkolivegreen|"
    r"darkorange|darkorchid|darkred|darksalmon|darkseagreen|darkslateblue|darkslategray|darkslategrey|"
    r"darkturquoise|darkviolet|deeppink|deepskyblue|dimgray|dimgrey|dodgerblue|firebrick|floralwhite|"
    r"forestgreen|fuchsia|gainsboro|ghostwhite|gold|goldenrod|gray|green|greenyellow|grey|honeydew|hotpink|"
    r"indianred|indigo|ivory|khaki|lavender|lavenderblush|lawngreen|lemonchiffon|lightblue|lightcoral|"
    r"lightcyan|lightgoldenrodyellow|lightgray|lightgreen|lightgrey|lightpink|lightsalmon|lightseagreen|"
    r"lightskyblue|lightslategray|lightslategrey|lightsteelblue|lightyellow|lime|limegreen|linen|magenta|"
    r"maroon|mediumaquamarine|mediumblue|mediumorchid|mediumpurple|mediumseagreen|mediumslateblue|"
    r"mediumspringgreen|mediumturquoise|mediumvioletred|midnightblue|mintcream|mistyrose|moccasin|navajowhite|"
    r"navy|oldlace|olive|olivedrab|orange|orangered|orchid|palegoldenrod|palegreen|paleturquoise|"
    r"palevioletred|papayawhip|peachpuff|peru|pink|plum|powderblue|purple|rebeccapurple|red|rosybrown|"
    r"royalblue|saddlebrown|salmon|sandybrown|seagreen|seashell|sienna|silver|skyblue|slateblue|slategray|"
    r"slategrey|snow|springgreen|steelblue|tan|teal|thistle|tomato|turquoise|violet|wheat|white|whitesmoke|"
    r"yellow|yellowgreen)(?![\w(-])",
    re.IGNORECASE,
)
#: Quoted values that are CSS machinery (attribute selectors on state), never copy.
STATE_STRINGS = {"", "true", "false", "dark", "light"}
SAFE_TAGS = {
    "a", "article", "b", "br", "button", "dd", "div", "dl", "dt", "em", "figcaption", "figure", "h1", "h2",
    "h3", "h4", "header", "hr", "i", "li", "ol", "p", "section", "small", "span", "strong", "sub", "sup",
    "table", "tbody", "td", "th", "thead", "tr", "ul",
}
FIXED_ATTRS = {"viewbox", "aria-hidden"}
SVG_SAMPLE = '<svg viewBox="0 0 24 24" aria-hidden="true"><!-- icon paths --></svg>'


class Refusal(ValueError):
    """The request cannot be written or filed as it stands."""


class LocalBlock(NamedTuple):
    name: str
    extends: Optional[str]
    purpose: str
    css: str


# ---- the deck's words ----------------------------------------------------------------------


class _Copy(HTMLParser):
    """Every piece of text a slide shows or announces."""

    SPOKEN = {"alt", "title", "aria-label", "placeholder"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self.skipping = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skipping += 1
        for key, value in attrs:
            if key in self.SPOKEN and value:
                self.parts.append(value)

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skipping:
            self.skipping -= 1

    def handle_data(self, data):
        if not self.skipping and data.strip():
            self.parts.append(data.strip())


def _words(text: str) -> List[str]:
    return [w.casefold() for w in WORD.findall(text)]


def _phrases(text: str) -> Set[Tuple[str, ...]]:
    words = _words(text)
    return {tuple(words[i : i + PHRASE_WORDS]) for i in range(len(words) - PHRASE_WORDS + 1)}


class DeckCopy:
    """The words, phrases and figures a request must not repeat."""

    def __init__(self, deck: Path, slides: Dict[str, str], catalog_names: Iterable[str]) -> None:
        shown: List[str] = []
        for html in slides.values():
            parser = _Copy()
            parser.feed(html)
            shown += parser.parts
        # A folder or file slug often carries the client's name, so it counts as deck wording too.
        slugs = [deck.resolve().name, *(Path(name).stem for name in slides)]
        self.words = {w for part in shown + slugs for w in _words(part)} - _generic_words(catalog_names)
        self.figures = {f for part in shown for f in FIGURE.findall(part)}
        self.phrases = set().union(*(_phrases(part) for part in shown))

    def leaks(self, text: str) -> List[str]:
        """Words, figures and copied phrases of the deck found in *text*."""
        found = sorted(set(_words(text)) & self.words)
        found += sorted(set(FIGURE.findall(text)) & self.figures)
        found += sorted(" ".join(p) for p in _phrases(text) & self.phrases)
        return found


def _generic_words(catalog_names: Iterable[str]) -> Set[str]:
    """The skill's own vocabulary: its documentation outside code samples, plus the catalog's names."""
    words: Set[str] = set(_words(" ".join([SAMPLE, SVG_SAMPLE, *catalog_names])))
    try:
        for path in [lint_deck.ASSETS.parent / "SKILL.md", *sorted(lint_deck.ASSETS.glob("*.md"))]:
            if path.is_file():
                words.update(_words(FENCED.sub("", path.read_text(encoding="utf-8"))))
    except (OSError, UnicodeDecodeError) as exc:
        raise lint_deck.CheckError(f"cannot read the skill's documentation: {exc}") from exc
    return words


# ---- what a request may contain ------------------------------------------------------------


def css_problems(css: str) -> List[str]:
    """Anything in *css* that is not built on the design tokens."""
    bare = lint_deck.COMMENT.sub("", css)
    problems = [f"quoted text '{a or b}'" for a, b in QUOTED.findall(bare) if (a or b) not in STATE_STRINGS]
    problems += [f"'{w}'" for w in ("url(", "@import", "@font-face") if w in bare.lower()]
    for rule in lint_deck.css_rules(bare, "request"):
        for declaration in rule.declarations.split(";"):
            prop, _, value = declaration.partition(":")
            prop, value = prop.strip().lower(), QUOTED.sub("", value).strip()
            if prop in ("font", "font-family") and value != "inherit":
                problems.append(f"literal font '{value}'")
            for pattern in (HEX_COLOUR, COLOUR_FUNCTION, NAMED_COLOUR):
                problems += [f"literal colour '{m.group(0)}' in '{prop}'" for m in pattern.finditer(value)]
    return problems


def css_names(css: str) -> str:
    """The text a person chose in *css*: selectors, at-rule names, custom properties and named values."""
    bare = lint_deck.COMMENT.sub("", css)
    chosen = AT_PRELUDE.findall(bare) + CUSTOM_PROPERTY.findall(bare)
    for rule in lint_deck.css_rules(bare, "request"):
        chosen.append(rule.selector)
        for declaration in rule.declarations.split(";"):
            prop, _, value = declaration.partition(":")
            if prop.strip().lower() in NAMING_PROPERTIES:
                chosen.append(value)
    return " ".join(chosen)


class _Written(HTMLParser):
    """The free text of sample markup: text nodes, comments and attribute values."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []

    def handle_starttag(self, tag, attrs):
        self.parts += [value for key, value in attrs if value and key not in FIXED_ATTRS]

    def handle_data(self, data):
        self.parts.append(data)

    def handle_comment(self, data):
        self.parts.append(data)


def request_problems(text: str, copy: DeckCopy) -> List[str]:
    """Why a request is not ready to file; empty when it is."""
    text = text.replace("\r\n", "\n")
    problems = ["a 'TODO' is still unfilled"] if "TODO" in text else []
    chosen = [FENCED.sub("", text)]
    for fence in FENCED.finditer(text):
        lang, body = fence.group("lang"), fence.group("body")
        if lang == "css":
            problems += css_problems(body)
            chosen.append(css_names(body))
        elif lang == "html":
            parser = _Written()
            parser.feed(body)
            chosen += parser.parts
        else:
            chosen.append(body)
    problems += [f"literal colour '{m.group(0)}'" for m in HEX_COLOUR.finditer(FENCED.sub("", text))]
    problems += [f"deck copy '{leak}'" for part in chosen for leak in copy.leaks(part)]
    return list(dict.fromkeys(problems))


# ---- sample markup -------------------------------------------------------------------------


class _Sample(HTMLParser):
    """The first element carrying a wanted class, rebuilt from tags and known class names only."""

    def __init__(self, wanted: Set[str], known: Set[str]) -> None:
        super().__init__(convert_charrefs=True)
        self.wanted, self.known = wanted, known
        self.lines: List[str] = []
        self.stack: List[Tuple[str, str]] = []
        self.svg_depth = 0
        self.done = False

    def _emit(self, line: str) -> None:
        self.lines.append("  " * len(self.stack) + line)

    def _close(self, safe: str) -> None:
        """Close an element, on one line when its text is all it holds."""
        text = "  " * (len(self.stack) + 1) + SAMPLE
        if len(self.lines) > 1 and self.lines[-1] == text and self.lines[-2].lstrip().startswith(f"<{safe}"):
            self.lines.pop()
            self.lines[-1] += f"{SAMPLE}</{safe}>"
        else:
            self._emit(f"</{safe}>")

    def handle_starttag(self, tag, attrs):
        if self.done:
            return
        if self.svg_depth:
            self.svg_depth += tag == "svg"
            return
        classes = (dict(attrs).get("class") or "").split()
        if not self.stack and not self.wanted & set(classes):
            return
        if tag == "svg":
            self._emit(SVG_SAMPLE)
            self.svg_depth = 1
            return
        if tag in lint_deck.VOID_TAGS and tag not in SAFE_TAGS:
            return
        safe = tag if tag in SAFE_TAGS else "div"
        kept = " ".join(c for c in classes if c in self.known)
        opening = f'<{safe} class="{kept}">' if kept else f"<{safe}>"
        self._emit(opening)
        if tag not in lint_deck.VOID_TAGS:
            self.stack.append((tag, safe))

    def handle_startendtag(self, tag, attrs):
        if not self.svg_depth:
            self.handle_starttag(tag, attrs)
            if tag not in lint_deck.VOID_TAGS:
                self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.done:
            return
        if self.svg_depth:
            self.svg_depth -= tag == "svg"
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                while len(self.stack) > i:
                    self._close(self.stack.pop()[1])
                self.done = not self.stack
                return

    def handle_data(self, data):
        if self.stack and not self.svg_depth and data.strip():
            self._emit(SAMPLE)


def sample_markup(htmls: List[str], wanted: Set[str], known: Set[str]) -> str:
    for html in htmls:
        parser = _Sample(wanted, known)
        parser.feed(html)
        if parser.lines:
            return "\n".join(parser.lines)
    raise Refusal(f"no element on any slide carries the block's classes ({', '.join(sorted(wanted)) or 'none'})")


# ---- generate and check --------------------------------------------------------------------


def read_slides(deck: Path) -> Dict[str, str]:
    try:
        return {p.name: p.read_text(encoding="utf-8") for p in lint_deck.slide_files(deck)}
    except (OSError, UnicodeDecodeError) as exc:
        raise lint_deck.CheckError(f"cannot read the deck: {exc}") from exc


def local_blocks(slides: Dict[str, str]) -> Dict[str, Tuple[LocalBlock, List[str]]]:
    """``{name: (block, [slide names])}``; one name must mean one block across the deck."""
    found: Dict[str, Tuple[LocalBlock, List[str]]] = {}
    for slide, html in slides.items():
        for match in lint_deck.LOCAL_BLOCK.finditer(html):
            name, body = match.group("name"), match.group("body")
            meta = lint_deck.LOCAL_META.match(body)
            if not meta:
                raise Refusal(f"{slide}: local block '{name}' lacks its '/* purpose: … · extends: … */' line")
            extends = meta.group("extends")
            css = lint_deck.COMMENT.sub("", body.replace("\r\n", "\n")).strip()
            block = LocalBlock(name, None if extends == "none" else extends, meta.group("purpose"), css)
            known = found.setdefault(name, (block, []))
            if (known[0].css.split(), known[0].extends) != (css.split(), block.extends):
                raise Refusal(f"local block '{name}' differs between {known[1][0]} and {slide}")
            known[1].append(slide)
    return found


def build_request(block: LocalBlock, htmls: List[str], titles: Dict[str, str], known: Set[str], template: str) -> str:
    if block.extends and block.extends not in titles:
        raise Refusal(f"local block '{block.name}' extends unknown component '{block.extends}'")
    own = {c for r in lint_deck.css_rules(block.css, "request") for c in r.classes()}
    target = f"{block.extends}.{block.name}" if block.extends else block.name
    return Template(template).substitute(
        name=block.name,
        target=target,
        kind=f"variant of `{block.extends}`" if block.extends else "new component",
        section=f"`{block.extends}` ({titles[block.extends]})" if block.extends else f"new section `{block.name}`",
        purpose=block.purpose,
        markup=sample_markup(htmls, own, own | known),
        css=block.css,
    )


def _catalog_names() -> Tuple[Dict[str, str], Set[str]]:
    """``({component id: title}, {class names the catalog and base zone own})``."""
    try:
        ledger = (lint_deck.ASSETS / "components.md").read_text(encoding="utf-8")
        template = (lint_deck.ASSETS / "template.html").read_text(encoding="utf-8")
        catalog = parse_catalog(ledger)
    except (OSError, ValueError) as exc:
        raise lint_deck.CheckError(f"cannot read the catalog: {exc}") from exc
    titles = {c["id"]: c["title"] for c in catalog["components"]}
    classes = {name for c in catalog["components"] for v in c["variants"] for name in v["classes"]}
    for zone in lint_deck.SHARED_ZONE.finditer(template):
        classes.update(owned_classes(zone.group(0)))
    return titles, classes


def generate(deck: Path) -> Tuple[List[Path], List[Path]]:
    """``(written, kept)`` request paths. Every request is built and checked before any is written."""
    slides = read_slides(deck)
    blocks = local_blocks(slides)
    titles, known = _catalog_names()
    copy = DeckCopy(deck, slides, [*titles, *titles.values(), *known])
    try:
        template = (lint_deck.ASSETS / TEMPLATE_FILE).read_text(encoding="utf-8")
    except OSError as exc:
        raise lint_deck.CheckError(f"cannot read {TEMPLATE_FILE}: {exc}") from exc
    pending: List[Tuple[Path, str]] = []
    kept: List[Path] = []
    problems: List[str] = []
    for name, (block, used_on) in sorted(blocks.items()):
        path = deck / f"{REQUEST_PREFIX}{name}.md"
        if path.exists():
            kept.append(path)
            continue
        if not lint_deck.report_path_untracked(path):
            raise lint_deck.CheckError(f"{deck} is inside a git work tree; a request never goes in a tracked path")
        text = build_request(block, [slides[s] for s in used_on], titles, known, template)
        found = [p for p in request_problems(text, copy) if not p.startswith("a 'TODO'")]
        problems += [f"local block '{name}': {p}" for p in found]
        pending.append((path, text))
    if problems:
        raise Refusal("\n".join(problems))
    for path, text in pending:
        save_text(path, text, encoding="utf-8", newline="\n")
    return [p for p, _ in pending], kept


def check(deck: Path) -> Dict[str, List[str]]:
    """``{request file name: problems}`` for every local block's request."""
    slides = read_slides(deck)
    titles, known = _catalog_names()
    copy = DeckCopy(deck, slides, [*titles, *titles.values(), *known])
    names = set(local_blocks(slides))
    names |= {p.stem[len(REQUEST_PREFIX) :] for p in deck.glob(f"{REQUEST_PREFIX}*.md")}
    report: Dict[str, List[str]] = {}
    for name in sorted(names):
        path = deck / f"{REQUEST_PREFIX}{name}.md"
        if not path.is_file():
            report[path.name] = ["not generated yet"]
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise lint_deck.CheckError(f"cannot read {path.name}: {exc}") from exc
        report[path.name] = request_problems(text, copy)
    return report


# ---- CLI -----------------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Write or check the component requests for a deck's local blocks.")
    parser.add_argument("deck", type=Path)
    parser.add_argument("--check", action="store_true", help="check the filled requests; write nothing")
    args = parser.parse_args(argv)
    try:
        if args.check:
            report = check(args.deck)
            for name, problems in report.items():
                log.info("%s %s", "❌" if problems else "✅", name)
                for problem in problems:
                    log.info("    %s", problem)
            if not report:
                log.info("ℹ️ no local blocks and no requests in the deck")
            return EXIT_REFUSED if any(report.values()) else EXIT_OK
        written, kept = generate(args.deck)
        for path in written:
            log.info("✅ wrote %s: fill its TODO lines, then run --check", path.name)
        for path in kept:
            log.info("ℹ️ kept %s (delete it to regenerate)", path.name)
        if not written and not kept:
            log.info("ℹ️ no local blocks in the deck")
        return EXIT_OK
    except Refusal as exc:
        log.error("❌ refused, nothing written:\n%s", exc)
        return EXIT_REFUSED
    except lint_deck.CheckError as exc:
        log.error("❌ could not check: %s", exc)
        return EXIT_UNKNOWN


if __name__ == "__main__":
    sys.exit(main())
