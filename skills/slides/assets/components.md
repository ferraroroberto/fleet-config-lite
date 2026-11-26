# slides · component catalog

Every slide is composed from these standard pieces, and only from them. This file is the ledger: each entry names a stable **id** and **version**, its purpose, when to use it and when not to, its named **variants**, and the worked HTML+CSS on the design-system tokens. Icons: copy exact path data from `icons.html` (hand-drawn SVG is banned).

**How a slide uses a component.** Copy the entry's markup and adapt the content, not the structure. Copy each CSS block **verbatim, anchors included**, into the per-slide zone below the `==slides:base==` anchor:

```css
/* ==slides:c:<id>[.<variant>]@<version>== */
…the catalog's rules, byte for byte…
/* ==/slides:c:<id>[.<variant>]@<version>== */
```

The anchor is how a slide declares which catalog pieces it uses, and the bytes inside it must stay identical to this file (`assets/catalog.json` records each block's hash). Never edit inside a component block: per-slide settings go through the component's **knobs** (custom properties set in a `style` attribute on the component's root, e.g. `<div class="tiles" style="--tiles-cols: 3">`). Component blocks are per-slide and are **not** propagated; deck-wide CSS belongs in the shared `==slides:*==` zones.

**Placement.** Give a slide's main content block the base-zone class `push` (`<div class="pipeline push">`) to centre it vertically: its `margin-top: auto` splits the leftover space evenly with the footer's own auto margin.

**Changing the catalog.** Edit the entry here, bump its version (in the id line and in every anchor of that component), then regenerate the index with `python <skill-dir>/scripts/build_catalog.py`. `catalog.json` is generated, never hand-edited; `build_catalog.py --check` fails when the two drift.

The examples under `assets/examples/` show these pieces composed into real slides: the pipeline + loopback on `s01`, tiles + band + reveal + mini-flow on `s02`, figures + divider + state cards on `s03`, the nav grid on `s00`.

## Chooser

Pick by the kind of message the slide carries; every slide also takes the header block and the footer strip.

| Message the slide carries | Component | Variant |
|---|---|---|
| Opening of every slide: label, title, thesis | `header` | `header` |
| A sequence read left to right, 3–7 short steps | `pipeline` | `pipeline`; `pipeline.final` when the last step is the outcome |
| A step in a sequence that repeats | `loopback` | `loopback` |
| A sequence read top to bottom, or steps that need a full sentence each | `rows` | `rows` |
| Benefits or value points, each one short idea | `tiles` | `tiles` |
| Key numbers, measured or `{{TOKEN}}`-pending | `figures` | `figures` |
| Current status as counts per state | `states` | `states` |
| Before/after, or a comparison of two options | `cases` | `cases` |
| The one evidence line, or a call to action | `band` | `band` |
| Depth behind the slide ("why it matters") that the slide works without | `reveal` | `reveal` |
| A small flow inside a reveal panel | `mini-flow` | `mini-flow` |
| Two sections on one slide that must not read as one mapping | `divider` | `divider` |
| Closing line of every slide | `footer` | `footer` |
| The deck index | `nav` | `nav` |

## 1. Header block

- **id:** `header` · **version:** 1
- **Purpose:** Opens every slide: eyebrow label, two-tone title, thesis line.
- **Use when:** Always; every content slide and the nav slide start with it.
- **Don't use when:** Never left out; a second header on one slide means the slide holds two ideas and must be split.
- **CSS:** base zone
- **Variants:**
  - `header`: eyebrow in a `.top` flex row (which allows a right-aligned addition later), title with exactly one `<span class="hl">` phrase, thesis line.

```html
<div class="top">
  <div class="eyebrow">Rollout</div>
</div>
<h1>Five steps from box to <span class="hl">first reading</span></h1>
<p class="thesis">Each site follows the same path, so every install looks the same.</p>
```

Styles are in the base zone (`.top`, `.eyebrow`, `h1`, `.hl`, `.thesis`). One `<span class="hl">` phrase per title, never the whole title.

## 2. Numbered pipeline

- **id:** `pipeline` · **version:** 1
- **Purpose:** A left-to-right sequence of steps: circle discs on a connector rail, number badges overhanging top-right.
- **Use when:** The message is an ordered process of 3–7 steps, each a short label plus one line.
- **Don't use when:** Steps need more than one line of text (use `rows`), the order does not matter (use `tiles`), or there are more than 7 steps (split the slide).
- **Knobs:** `--pipeline-cols` (step count, default 5), `--pipeline-step-w` (subline max-width, default `16cqw`; about `13.5cqw` at 7 steps, `22cqw`–`28cqw` at 3).
- **Variants:**
  - `pipeline`: the base pipeline; every step looks the same.
  - `pipeline.final`: the terminal step takes `.final` (solid accent fill, `--on-accent` icon) with the badge contrast inversion; use it with the base block when the last step is the outcome.

```html
<div class="pipeline">
  <div class="rail"></div>
  <div class="row">
    <div class="step">
      <div class="disc"><svg viewBox="0 0 24 24" aria-hidden="true"><!-- icon paths --></svg><span class="badge">1</span></div>
      <h3>Unbox</h3>
      <p>Kit arrives with parts pre-labelled per site</p>
    </div>
    <!-- … steps 2–4 … -->
    <div class="step final">
      <div class="disc"><svg viewBox="0 0 24 24" aria-hidden="true"><!-- icon paths --></svg><span class="badge">5</span></div>
      <h3>Go live</h3>
      <p>Dashboard starts recording within the hour</p>
    </div>
  </div>
</div>
```

The rail insets `100% / (2 * cols)` each side, so it starts and ends at the first and last disc centres for any step count.

```css
/* ==slides:c:pipeline@1== */
.pipeline { position: relative; margin-top: 3.4cqw; }
.pipeline .rail { position: absolute; top: 3.4cqw; left: calc(100% / (2 * var(--pipeline-cols, 5))); right: calc(100% / (2 * var(--pipeline-cols, 5))); height: 2px; background: var(--line); }
.pipeline .row { position: relative; display: grid; grid-template-columns: repeat(var(--pipeline-cols, 5), 1fr); gap: 1.2cqw; }
.step { text-align: center; }
.disc { position: relative; width: 6.8cqw; height: 6.8cqw; margin: 0 auto; border-radius: 50%; background: var(--soft); border: 2px solid var(--accent); display: grid; place-items: center; }
.disc svg { width: 3.2cqw; height: 3.2cqw; color: var(--accent); }
.badge { position: absolute; top: -.5cqw; right: -.5cqw; width: 2.2cqw; height: 2.2cqw; border-radius: 50%; background: var(--deep); color: var(--slide); display: grid; place-items: center; font-size: 1.3cqw; font-weight: 700; font-variant-numeric: tabular-nums; }
.step h3 { font-size: 2cqw; font-weight: 700; margin: 1.1cqw 0 .35cqw; }
.step p { font-size: 1.55cqw; line-height: 1.35; color: var(--muted); margin: 0 auto; max-width: var(--pipeline-step-w, 16cqw); }
/* ==/slides:c:pipeline@1== */
```

**Badge contrast inversion (hard rule):** on an accent-filled disc the badge inverts — light theme `background: var(--ink); color: var(--slide)`; dark theme overrides again, **in both dark blocks**, to `background: var(--bg); color: var(--ink)`. Accent-on-accent never ships.

```css
/* ==slides:c:pipeline.final@1== */
.step.final .disc { background: var(--accent); }
.step.final .disc svg { color: var(--on-accent); }
.step.final .badge { background: var(--ink); color: var(--slide); }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) .step.final .badge { background: var(--bg); color: var(--ink); }
}
:root[data-theme="dark"] .step.final .badge { background: var(--bg); color: var(--ink); }
/* ==/slides:c:pipeline.final@1== */
```

## 3. Loopback bracket

- **id:** `loopback` · **version:** 1
- **Purpose:** A dashed bracket under a pipeline with a centred label, marking a step that repeats.
- **Use when:** A pipeline has one step, or a stretch of steps, that recurs on a cycle.
- **Don't use when:** There is no pipeline above it, or the whole process is a loop (say so in the thesis instead).
- **Knobs:** `--loopback-cols` (the pipeline's step count, default 5, so the bracket lines up with the first and last disc).
- **Variants:**
  - `loopback`: left/right/bottom dashed border, rounded bottom corners, label on an opaque `--slide` background breaking the dash.

```html
<div class="loopback"><span>Calibration repeats at the start of each season</span></div>
```

```css
/* ==slides:c:loopback@1== */
.loopback { position: relative; margin: 2cqw calc(100% / (2 * var(--loopback-cols, 5))) 0; height: 2.8cqw; border: 2px dashed var(--line); border-top: none; border-radius: 0 0 12px 12px; }
.loopback span { position: absolute; left: 50%; bottom: -1cqw; transform: translateX(-50%); background: var(--slide); padding: 0 1cqw; font-size: 1.4cqw; color: var(--muted); white-space: nowrap; }
/* ==/slides:c:loopback@1== */
```

## 4. Progressive reveal

- **id:** `reveal` · **version:** 1
- **Purpose:** A pill ghost button that opens a hidden panel of supporting depth.
- **Use when:** There is "why it matters" depth the presenter may want to open, and the slide is fully understandable without it.
- **Don't use when:** The panel would hold content the slide needs, or the slide already fills the frame with the panel open (reveals are verified expanded and must still fit).
- **Variants:**
  - `reveal`: `aria-expanded` drives a chevron rotation; a two-class JS animation (`.open` sets `display`, `.in` on a **double `requestAnimationFrame`** triggers the fade/slide); close is instant. `prefers-reduced-motion` neutralises all transitions (base zone).

```html
<div class="reveal">
  <button class="reveal-btn" type="button" aria-expanded="false" aria-controls="why">Why it matters <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></button>
  <div class="reveal-panel" id="why">
    <p>Every reading flows the same way, so one glance answers what used to take a site visit.</p>
  </div>
</div>
```

```css
/* ==slides:c:reveal@1== */
.reveal { margin-top: 1.6cqw; }
.reveal-btn { display: inline-flex; align-items: center; gap: .6cqw; font-size: 1.4cqw; font-weight: 600; font-family: inherit; color: var(--accent); background: transparent; border: 1px solid var(--line); border-radius: 999px; padding: .55cqw 1.4cqw; cursor: pointer; }
.reveal-btn svg { width: 1.4cqw; height: 1.4cqw; transition: transform .25s ease; }
.reveal-btn[aria-expanded="true"] svg { transform: rotate(180deg); }
.reveal-panel { display: none; opacity: 0; transform: translateY(.8cqw); transition: opacity .3s ease, transform .3s ease; margin-top: 1.2cqw; }
.reveal-panel.open { display: block; }
.reveal-panel.in { opacity: 1; transform: none; }
.reveal-panel p { font-size: 1.55cqw; line-height: 1.35; color: var(--muted); margin: 0 0 .9cqw; }
/* ==/slides:c:reveal@1== */
```

```html
<script>
  (function () {
    var btn = document.querySelector(".reveal-btn");
    if (!btn) return;
    var panel = document.getElementById(btn.getAttribute("aria-controls"));
    btn.addEventListener("click", function () {
      var open = btn.getAttribute("aria-expanded") === "true";
      if (open) {
        btn.setAttribute("aria-expanded", "false");
        panel.classList.remove("open", "in");
        return;
      }
      btn.setAttribute("aria-expanded", "true");
      panel.classList.add("open");
      requestAnimationFrame(function () {
        requestAnimationFrame(function () { panel.classList.add("in"); });
      });
    });
  })();
</script>
```

## 5. Value tiles

- **id:** `tiles` · **version:** 1
- **Purpose:** A row of `--soft` cards, each a centred icon, heading and one-line body.
- **Use when:** The message is a set of parallel benefits or value points, 3–5 of them, each one short idea.
- **Don't use when:** The points have an order (use `pipeline` or `rows`), carry numbers (use `figures`), or need more than one line each (use `cases`).
- **Knobs:** `--tiles-cols` (tile count per row, default 4).
- **Variants:**
  - `tiles`: 10px radius cards on the standard `1.2cqw` gap.

```html
<div class="tiles">
  <div class="tile"><svg viewBox="0 0 24 24" aria-hidden="true"><!-- icon --></svg>
    <h3>Earlier warnings</h3>
    <p>Drift shows up before plants do</p>
  </div>
  <!-- … more tiles … -->
</div>
```

```css
/* ==slides:c:tiles@1== */
.tiles { display: grid; grid-template-columns: repeat(var(--tiles-cols, 4), 1fr); gap: 1.2cqw; margin-top: 2.6cqw; }
.tile { background: var(--soft); border-radius: 10px; padding: 1.6cqw 1.4cqw; text-align: center; }
.tile svg { width: 2.6cqw; height: 2.6cqw; color: var(--accent); }
.tile h3 { font-size: 1.75cqw; font-weight: 700; margin: .7cqw 0 .35cqw; }
.tile p { font-size: 1.4cqw; color: var(--muted); margin: 0; }
/* ==/slides:c:tiles@1== */
```

## 6. Evidence / figure strip

- **id:** `figures` · **version:** 1
- **Purpose:** A row of large tabular-nums figures with captions.
- **Use when:** The message is carried by 2–4 key numbers, verified or still `{{TOKEN}}` placeholders.
- **Don't use when:** The numbers are counts per state (use `states`), or there is a single number that is the slide's point (put it in a `band`).
- **Knobs:** `--figures-cols` (figure count, default 3).
- **Variants:**
  - `figures`: `minmax(0, 1fr)` tracks with `overflow-wrap: anywhere`, so an unfilled `{{TOKEN}}` cannot blow the layout. When figures sit near a steps row, separate them with a `divider` so no 1:1 mapping is implied.

```html
<div class="figures">
  <div class="figure"><div class="num">14</div><div class="cap">sites live through the season</div></div>
  <div class="figure"><div class="num">{{HOURS_SAVED}}</div><div class="cap">team hours saved per week</div></div>
</div>
```

```css
/* ==slides:c:figures@1== */
.figures { display: grid; grid-template-columns: repeat(var(--figures-cols, 3), minmax(0, 1fr)); gap: 1.2cqw; margin-top: 2.6cqw; }
.figure { text-align: center; }
.figure .num { font-size: 3.4cqw; font-weight: 700; font-variant-numeric: tabular-nums; color: var(--accent); overflow-wrap: anywhere; }
.figure .cap { font-size: 1.4cqw; color: var(--muted); margin-top: .35cqw; }
/* ==/slides:c:figures@1== */
```

## 7. Case cards

- **id:** `cases` · **version:** 1
- **Purpose:** Two half-width cards with bullet lists, side by side.
- **Use when:** The message is a before/after or a comparison of two options, point by point.
- **Don't use when:** There are more than two sides (use `tiles`), or the points are numbers (use `figures`).
- **Variants:**
  - `cases`: `text-wrap: balance` on multi-line bullets; **sibling cards follow the same bullet sequence** — a change in one changes all.

```html
<div class="cases">
  <div class="case">
    <h3>Before</h3>
    <ul>
      <li>Weekly drive to every site</li>
      <li>Readings logged by hand</li>
      <li>Problems found on arrival</li>
    </ul>
  </div>
  <div class="case">
    <h3>After</h3>
    <ul>
      <li>Weekly drive only when flagged</li>
      <li>Readings logged automatically</li>
      <li>Problems flagged before the drive</li>
    </ul>
  </div>
</div>
```

```css
/* ==slides:c:cases@1== */
.cases { display: grid; grid-template-columns: repeat(2, 1fr); gap: 1.2cqw; margin-top: 2.6cqw; }
.case { background: var(--soft); border-radius: 10px; padding: 1.6cqw 1.4cqw; }
.case h3 { font-size: 1.75cqw; font-weight: 700; margin: 0 0 .7cqw; }
.case ul { margin: 0; padding-left: 2cqw; }
.case li { font-size: 1.4cqw; color: var(--muted); line-height: 1.35; margin-top: .45cqw; text-wrap: balance; }
/* ==/slides:c:cases@1== */
```

## 8. State cards

- **id:** `states` · **version:** 1
- **Purpose:** Equal compact cards, each a single count and its state label, content vertically centred.
- **Use when:** The message is where things stand: how many items sit in each state.
- **Don't use when:** The numbers are not counts of one population (use `figures`), or a card would need more than one number.
- **Knobs:** `--states-cols` (state count, default 3).
- **Variants:**
  - `states`: single numbers only.

```html
<div class="states">
  <div class="state"><div class="count">14</div><div class="label">Live</div></div>
  <div class="state"><div class="count">4</div><div class="label">Installing</div></div>
  <div class="state"><div class="count">9</div><div class="label">Scheduled</div></div>
</div>
```

```css
/* ==slides:c:states@1== */
.states { display: grid; grid-template-columns: repeat(var(--states-cols, 3), 1fr); gap: 1.2cqw; margin-top: 1.2cqw; }
.state { background: var(--soft); border-radius: 10px; padding: 1.4cqw; min-height: 8cqw; display: flex; flex-direction: column; justify-content: center; text-align: center; }
.state .count { font-size: 2.8cqw; font-weight: 700; font-variant-numeric: tabular-nums; }
.state .label { font-size: 1.4cqw; color: var(--muted); margin-top: .25cqw; }
/* ==/slides:c:states@1== */
```

## 9. Stacked rows

- **id:** `rows` · **version:** 1
- **Purpose:** Full-width numbered horizontal cards, one per step.
- **Use when:** A sequence reads top to bottom, or each step needs a heading plus a full sentence.
- **Don't use when:** The steps are short enough for a `pipeline`, or there are more than 4 (they will not fit the frame).
- **Variants:**
  - `rows`: number disc, heading and one line per card.

```html
<div class="rows">
  <div class="rowcard"><span class="n">1</span>
    <div><h3>Survey the site</h3><p>One visit, one checklist, photos of every mount point</p></div>
  </div>
  <!-- … more rows … -->
</div>
```

```css
/* ==slides:c:rows@1== */
.rows { display: grid; gap: 1.2cqw; margin-top: 2.6cqw; }
.rowcard { display: flex; align-items: center; gap: 1.4cqw; background: var(--soft); border-radius: 10px; padding: 1.4cqw 1.6cqw; }
.rowcard .n { width: 3.2cqw; height: 3.2cqw; border-radius: 50%; background: var(--deep); color: var(--slide); display: grid; place-items: center; font-size: 1.4cqw; font-weight: 700; font-variant-numeric: tabular-nums; flex: none; }
.rowcard h3 { font-size: 1.75cqw; font-weight: 700; margin: 0; }
.rowcard p { font-size: 1.4cqw; color: var(--muted); margin: .2cqw 0 0; }
/* ==/slides:c:rows@1== */
```

## 10. Highlight band

- **id:** `band` · **version:** 1
- **Purpose:** An accent-tinted full-width band holding one sentence.
- **Use when:** The slide has one key evidence line, or closes on a call to action.
- **Don't use when:** It would repeat the thesis, or a slide would carry two bands (one key line per slide).
- **Variants:**
  - `band`: same internal padding as adjacent cards.

```html
<div class="band">Teams report the first useful alert within {{FIRST_ALERT_DAYS}}&nbsp;days of go-live.</div>
```

```css
/* ==slides:c:band@1== */
.band { background: var(--soft); border-left: 4px solid var(--accent); border-radius: 10px; padding: 1.6cqw 1.4cqw; margin-top: 1.6cqw; font-size: 1.75cqw; }
/* ==/slides:c:band@1== */
```

## 11. Mini-flow

- **id:** `mini-flow` · **version:** 1
- **Purpose:** A compact centred 3-step flow with accent arrows.
- **Use when:** A reveal panel needs to show a small flow (data path, hand-off chain).
- **Don't use when:** The flow is the slide's main message (use `pipeline`), or it has more than 4 steps.
- **Variants:**
  - `mini-flow`: fixed narrow chips, `justify-content: center`.

```html
<div class="mini-flow">
  <span class="mini-step">Sensor</span>
  <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>
  <span class="mini-step">Gateway</span>
  <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>
  <span class="mini-step">Dashboard</span>
</div>
```

```css
/* ==slides:c:mini-flow@1== */
.mini-flow { display: flex; justify-content: center; align-items: center; gap: 1cqw; }
.mini-step { background: var(--soft); border-radius: 8px; padding: .8cqw 1.2cqw; font-size: 1.4cqw; font-weight: 600; }
.mini-flow svg { width: 1.6cqw; height: 1.6cqw; color: var(--accent); flex: none; }
/* ==/slides:c:mini-flow@1== */
```

## 12. Section divider

- **id:** `divider` · **version:** 1
- **Purpose:** A hairline rule followed by an eyebrow-style section heading, splitting a slide into two labelled parts.
- **Use when:** Two blocks share a slide but must not read as one mapping (figures near a row of states or steps).
- **Don't use when:** The two parts are two ideas (split the slide), or the first block needs no separation.
- **Variants:**
  - `divider`: `<hr class="divider">` then `<div class="section-h">`.

```html
<hr class="divider">
<div class="section-h">Where the sites stand</div>
```

```css
/* ==slides:c:divider@1== */
.divider { height: 1px; background: var(--line); margin: 2.2cqw 0 0; border: none; }
.section-h { font-size: 1.5cqw; font-weight: 600; text-transform: uppercase; letter-spacing: .16em; color: var(--accent); margin: 1.6cqw 0 0; }
/* ==/slides:c:divider@1== */
```

## 13. Footer strip

- **id:** `footer` · **version:** 1
- **Purpose:** Closes every slide: one icon and one muted sentence, pinned via `margin-top: auto`.
- **Use when:** Always; every content slide ends with it, in an identical format.
- **Don't use when:** Never left out. No bold, no separators beyond a middot, never time expectations.
- **CSS:** base zone
- **Variants:**
  - `footer`: icon plus one sentence.

```html
<div class="footer">
  <svg viewBox="0 0 24 24" aria-hidden="true"><!-- icon --></svg>
  <span>Fieldkit rollout · one path for every site.</span>
</div>
```

Styles are in the base zone (`.footer`).

## 14. Nav / index slide (`s00`)

- **id:** `nav` · **version:** 1
- **Purpose:** The deck index: eyebrow, title and a grid of link cards (number disc, name, one-line subtitle); keys 1–9 open slides.
- **Use when:** Always, once per deck, as `s00-nav.html`.
- **Don't use when:** On a content slide; navigation is never documented on any slide.
- **Knobs:** `--nav-cols` (cards per row, default 3).
- **Variants:**
  - `nav`: the link-card grid plus the index keyboard script.

```html
<div class="deck-grid">
  <a class="deck-card" href="s01-rollout.html">
    <span class="n">01</span>
    <span><h3>How the rollout works</h3>
    <p>Five steps from box to first reading</p></span>
  </a>
  <!-- … one card per slide … -->
</div>
```

```css
/* ==slides:c:nav@1== */
.deck-grid { display: grid; grid-template-columns: repeat(var(--nav-cols, 3), 1fr); gap: 1.2cqw; margin-top: 3cqw; }
.deck-card { display: flex; align-items: center; gap: 1.2cqw; background: var(--soft); border-radius: 10px; padding: 1.6cqw 1.4cqw; text-decoration: none; color: var(--ink); }
.deck-card .n { width: 3.2cqw; height: 3.2cqw; border-radius: 50%; background: var(--deep); color: var(--slide); display: grid; place-items: center; font-size: 1.4cqw; font-weight: 700; font-variant-numeric: tabular-nums; flex: none; }
.deck-card h3 { font-size: 1.75cqw; font-weight: 700; margin: 0; }
.deck-card p { font-size: 1.3cqw; color: var(--muted); margin: .25cqw 0 0; }
.deck-card:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
/* ==/slides:c:nav@1== */
```

```html
<!-- deck-nav -->
<script>
  (function () {
    var slides = ["s01-rollout.html", "s02-value.html", "s03-pilot.html"];
    document.addEventListener("keydown", function (e) {
      var n = parseInt(e.key, 10);
      if (n >= 1 && n <= slides.length) location.href = slides[n - 1];
    });
  })();
</script>
```

### Per-slide nav script

Appended to every content slide, marked `<!-- deck-nav -->` (the marker is what keeps it findable and propagatable):

```html
<!-- deck-nav -->
<script>
  (function () {
    var slides = ["s01-rollout.html", "s02-value.html", "s03-pilot.html"];
    var here = location.pathname.split("/").pop().toLowerCase();
    var i = slides.indexOf(here);
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" || e.key === "Home") { location.href = "s00-nav.html"; return; }
      var isSpace = e.key === " ";
      if (isSpace && document.activeElement && document.activeElement.tagName === "BUTTON") return;
      var d = 0;
      if (e.key === "ArrowRight" || e.key === "PageDown" || isSpace) d = 1;
      else if (e.key === "ArrowLeft" || e.key === "PageUp") d = -1;
      else return;
      e.preventDefault();
      if (i === -1) return;
      var j = i + d;
      if (j < 0) { location.href = "s00-nav.html"; return; }
      if (j >= slides.length) return;
      location.href = slides[j];
    });
  })();
</script>
```

Navigation is functional but **never documented on any slide** — presenter knowledge only.
