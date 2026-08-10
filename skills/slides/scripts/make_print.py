"""Compile a deck's slide files into one ``print.html`` (and optionally a PDF).

    python make_print.py <deck-dir> [--out print.html] [--pdf [deck.pdf]] [--chrome <path>]

Every ``sNN-*.html`` in the deck dir, in filename order, becomes one printed
page: light theme forced, progressive reveals forced open, theme toggle and
keyboard nav suppressed. What expands on screen must appear on paper.

How isolation works: each slide's markup and styles are embedded in their own
declarative shadow root (``<template shadowrootmode="open">``), so per-slide
CSS never collides across slides and no JavaScript is needed at load. The
slide CSS's ``:root`` selectors are rewritten to ``:host``; the theme-override
selectors stop matching in the process, which is precisely what forces the
light-base tokens. Page geometry is ``@page { size: 338mm 190mm landscape }``
(exact 16:9), one slide per page via ``page-break-after``.

Stdlib only, by design (this repo keeps no virtualenv). The optional PDF step
shells out to Chrome headless.
"""

from __future__ import annotations

import argparse
import logging
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

if sys.platform == "win32":  # emoji-safe output under piped/redirected capture
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("make_print")

SLIDE_FILE = re.compile(r"^s\d\d.*\.html$", re.IGNORECASE)
STYLE_RE = re.compile(r"<style[^>]*>(.*?)</style>", re.DOTALL | re.IGNORECASE)
BODY_RE = re.compile(r"<body[^>]*>(.*)</body>", re.DOTALL | re.IGNORECASE)
SCRIPT_RE = re.compile(r"<script\b.*?</script>", re.DOTALL | re.IGNORECASE)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.DOTALL | re.IGNORECASE)

CHROME_CANDIDATES = (
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
)

# Applied inside every slide's shadow root, after its own CSS.
PRINT_OVERRIDES = """
:host { display: grid; place-items: center; }
.theme-toggle { display: none !important; }
.reveal-panel {
  display: block !important;
  opacity: 1 !important;
  transform: none !important;
}
.reveal-btn { display: none !important; }
"""

PAGE_SHELL = """<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
@page {{ size: 338mm 190mm landscape; margin: 0; }}
html, body {{ margin: 0; padding: 0; background: #ffffff; }}
.page {{
  width: 338mm; height: 190mm; overflow: hidden;
  page-break-after: always; break-after: page;
}}
</style>
</head>
<body>
{pages}
</body>
</html>
"""


def rewrite_css(css: str) -> str:
    """Point the slide's root-level rules at the shadow host.

    ``:root { --tokens }`` must style the host to keep custom properties
    alive inside the shadow tree. The dark/light *override* selectors
    (``:root[data-theme=...]``, ``:root:not(...)``) become host-compound
    forms that never match the print host, so only the light base tokens
    survive. That is the mechanism that forces the light theme.
    """
    return css.replace(":root", ":host")


def compile_slide(path: Path) -> str:
    """Return one shadow-rooted ``.page`` element for a slide file."""
    text = path.read_text(encoding="utf-8")
    styles = STYLE_RE.findall(text)
    body_m = BODY_RE.search(text)
    if not styles or not body_m:
        raise SystemExit(
            f"❌ {path.name}: expected at least one <style> block and a <body>; "
            f"is this a slide file?"
        )
    body = SCRIPT_RE.sub("", body_m.group(1))
    if 'class="slide"' not in body and "class='slide'" not in body:
        raise SystemExit(f"❌ {path.name}: no .slide frame found in <body>.")
    css = rewrite_css("\n".join(styles))
    return (
        '<div class="page" data-theme="light">'
        '<template shadowrootmode="open">'
        f"<style>{css}</style><style>{PRINT_OVERRIDES}</style>"
        f"{body}"
        "</template></div>"
    )


def find_chrome(explicit: Optional[str]) -> Optional[str]:
    if explicit:
        return explicit if Path(explicit).is_file() else None
    for cand in CHROME_CANDIDATES:
        if Path(cand).is_file():
            return cand
    return None


def make_print(
    deck_dir: Path,
    out_name: str = "print.html",
    pdf: Optional[str] = None,
    chrome: Optional[str] = None,
) -> Path:
    """Compile the deck at *deck_dir*; return the written print.html path."""
    if not deck_dir.is_dir():
        raise SystemExit(f"❌ deck dir not found: {deck_dir}")
    slides = sorted(
        p for p in deck_dir.iterdir() if SLIDE_FILE.match(p.name)
    )
    if not slides:
        raise SystemExit(f"❌ no sNN-*.html slide files in {deck_dir}")

    pages = "\n".join(compile_slide(p) for p in slides)
    first_title = TITLE_RE.search(slides[0].read_text(encoding="utf-8"))
    deck_title = first_title.group(1).split("·")[0].strip() if first_title else deck_dir.name
    out = deck_dir / out_name
    out.write_text(
        PAGE_SHELL.format(title=f"{deck_title} · print", pages=pages),
        encoding="utf-8",
        newline="",
    )
    log.info("✅ wrote %s (%d slide page(s)).", out, len(slides))

    if pdf is not None:
        chrome_exe = find_chrome(chrome)
        if not chrome_exe:
            raise SystemExit(
                "❌ Chrome not found for --pdf (looked in the usual install "
                "paths; pass --chrome <path>). print.html was still written."
            )
        pdf_path = deck_dir / (pdf or "deck.pdf")
        cmd = [
            chrome_exe,
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--print-to-pdf-no-header",
            f"--print-to-pdf={pdf_path}",
            out.resolve().as_uri(),
        ]
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
            creationflags=creationflags,
        )
        if result.returncode != 0 or not pdf_path.is_file():
            raise SystemExit(
                f"❌ Chrome PDF export failed (exit {result.returncode}): "
                f"{result.stderr.strip()[:500]}"
            )
        log.info("✅ wrote %s.", pdf_path)
    return out


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("deck_dir", type=Path, help="folder holding the deck's sNN-*.html files")
    parser.add_argument("--out", default="print.html", help="output filename (default print.html)")
    parser.add_argument("--pdf", nargs="?", const="deck.pdf", default=None,
                        help="also export a PDF via Chrome headless (optional filename)")
    parser.add_argument("--chrome", default=None, help="explicit path to the Chrome executable")
    args = parser.parse_args(argv[1:])
    make_print(args.deck_dir, args.out, args.pdf, args.chrome)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
