# slides · design system (normative)

The single source for the deck's visual contract. `template.html` implements all of it; this file explains the rules a builder must not break. Everything mechanical about applying it deck-wide belongs to `scripts/propagate.py`, never to hand edits.

## Frame and body

Fullscreen presentation mode: exact 16:9 fill, letterboxed on any other ratio.

```css
body {
  background: var(--bg); min-height: 100vh; margin: 0; overflow: hidden;
  display: grid; place-items: center; padding: 0;
  font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
}
.slide {
  width: min(100vw, calc(100vh * 16 / 9));
  aspect-ratio: 16 / 9;
  container-type: inline-size;
  background: var(--slide); color: var(--ink);
  display: flex; flex-direction: column;
  padding: 3.2cqw 3.6cqw 2.4cqw; box-sizing: border-box; overflow: hidden;
}
svg { stroke: currentColor; fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
```

- **All internal sizes in `cqw`** (container-query units) — the slide renders identically at any pixel size.
- No border or radius on the frame; the footer pins via `margin-top: auto`.
- **Fit contract: "must fit, never scroll."** `overflow: hidden` clips silently, so density is tuned via cqw and copy edits, never via layout hacks.

## Single-source color

Two constants drive everything; every other tone derives. The shipped placeholder is a **deep green** — deliberately not a typical corporate blue, so it can never be mistaken for a real client color and visibly demands replacement. Real client values are set per engagement in this skill's gitignored `context/`, never in a tracked file.

```css
:root {
  /* SINGLE source of brand color — replace per client in private context */
  --brand: #1F7A54;       /* placeholder: deep green */
  --brand-dark: #0B2E21;  /* placeholder: deep green-black */

  /* light bases */
  --bg: color-mix(in srgb, var(--brand) 8%, #ffffff);
  --slide: #ffffff;
  --ink: var(--brand-dark);
  --accent: var(--brand);
  --deep: var(--brand-dark);
  --on-accent: #ffffff;

  /* derived, theme-agnostic — recompute automatically per theme */
  --muted: color-mix(in srgb, var(--ink) 68%, var(--slide));
  --faint: color-mix(in srgb, var(--ink) 50%, var(--slide));
  --soft:  color-mix(in srgb, var(--accent) 12%, var(--slide));
  --line:  color-mix(in srgb, var(--accent) 25%, var(--slide));
}
```

## Dark theme

Overrides **only the six bases**, in **both** dark blocks — `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {…} }` *and* `:root[data-theme="dark"]` — with the light values repeated in `:root[data-theme="light"]`, so the explicit toggle beats the OS preference in both directions.

```css
--bg: color-mix(in srgb, var(--brand-dark) 30%, #000000);
--slide: color-mix(in srgb, var(--brand-dark) 55%, #000000);
--ink: color-mix(in srgb, var(--brand) 12%, #ffffff);
--accent: oklch(from var(--brand) calc(l + 0.16) c h);
--deep: oklch(from var(--brand) calc(l + 0.30) c h);
--on-accent: var(--bg);
```

**Hue-preservation rule (hard):** never lighten the brand color for dark mode by sRGB-mixing toward white — it desaturates the identity into a generic pastel. Brand-carrying tokens (`--accent`, `--deep`) lighten via `oklch(from …)` relative color, which preserves hue and chroma. Neutrals may use sRGB mixes.

## Theme bootstrap

First script in every file. The localStorage key is namespaced per deck and identical across a deck's files, so the choice carries between slides:

```html
<script>
  (function () {
    var t = null;
    try { t = localStorage.getItem("<deck-key>.theme"); } catch (e) {}
    if (t !== "dark" && t !== "light") {
      t = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }
    document.documentElement.setAttribute("data-theme", t);
  })();
</script>
```

## Theme toggle

Fixed top-right (`top: 1rem; right: 1rem` — symmetric), 40×40px circle, `var(--slide)` fill, `1px solid var(--line)`, two inline SVGs (moon/sun) swapped purely via `data-theme` CSS selectors, hidden in `@media print`, `:focus-visible` outline in accent.

## Typography (all cqw)

| Element | Size | Weight / treatment |
|---|---|---|
| Eyebrow | `1.5` | 600, uppercase, `.16em` tracking, accent |
| Title `h1` | `3.1` | 700, `-.015em`, line-height 1.1, ink |
| Title accent | — | exactly **one** `<span class="hl">` phrase per title |
| Thesis | `2` | muted |
| Step label | `2` | 700 |
| Step subline | `1.55` | muted, line-height 1.35 |
| Number badge | `1.3` | 700, tabular-nums |
| Tile heading | `1.75` | 700 |
| Tile body | `1.4` | muted |
| Footer | `1.6` | muted, tabular-nums |

## Spacing

- Frame padding `3.2 / 3.6 / 2.4` cqw.
- Major block transitions: 1.1–3.4cqw.
- Micro spacing within a text cluster: .25–.9cqw.
- **Standard gap between adjacent cards/tiles: `1.2cqw`, deck-wide.**
- Band-style pieces use the same internal padding as neighboring cards.

## Self-containment (no server, ever)

All CSS, JS and icons inline; **zero external requests; no webfonts**. That is the portability guarantee: any slide file opens from disk, anywhere, forever. Icons come from `icons.html` (vendored Lucide path data) — copy paths, never hand-draw and never hotlink.

## Working model

Multi-file for authoring and presenting — one HTML file per slide plus an `s00` nav/index — for regeneration granularity, per-frame fit verification and failure isolation. Single-file exists only as the compiled print/PDF export (`scripts/make_print.py`). Shared-zone changes propagate via `scripts/propagate.py` against the `==slides:*==` anchors; the anchors are part of the design system and must survive in every generated slide.
