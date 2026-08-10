# slides · component catalog

Every slide is composed from these standard pieces. Each entry carries complete worked HTML+CSS on the design-system tokens; copy the worked code and adapt content, not structure. Icons: copy exact path data from `icons.html` (hand-drawn SVG is banned). Layout CSS lives in the per-slide zone below the `==slides:base==` anchor and is **not** propagated; anything shared deck-wide belongs in the anchored zones.

The examples under `assets/examples/` show these pieces composed into real slides: the pipeline + loopback on `s01`, tiles + band + reveal + mini-flow on `s02`, figures + state cards on `s03`, the nav grid on `s00`.

## 1. Header block

Eyebrow (in a `.top` flex row, which allows a right-aligned addition later) + two-tone title + thesis line. One `<span class="hl">` phrase per title, never the whole title.

```html
<div class="top">
  <div class="eyebrow">Rollout</div>
</div>
<h1>Five steps from box to <span class="hl">first reading</span></h1>
<p class="thesis">Each site follows the same path, so every install looks the same.</p>
```

Styles are in the base zone (`.top`, `.eyebrow`, `h1`, `.hl`, `.thesis`).

## 2. Numbered pipeline

N circle discs on a connector line; number badges overhang top-right; the terminal step may take `.final` (solid accent fill, `--on-accent` icon). The rail insets `calc(100% / (2*N))` each side so it starts and ends at the first/last disc centers — for N=5 that is `calc(100% / 10)`.

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

```css
.pipeline { position: relative; margin-top: 3.4cqw; }
.pipeline .rail { position: absolute; top: 3.4cqw; left: calc(100% / 10); right: calc(100% / 10); height: 2px; background: var(--line); }
.pipeline .row { position: relative; display: grid; grid-template-columns: repeat(5, 1fr); gap: 1.2cqw; }
.step { text-align: center; }
.disc { position: relative; width: 6.8cqw; height: 6.8cqw; margin: 0 auto; border-radius: 50%; background: var(--soft); border: 2px solid var(--accent); display: grid; place-items: center; }
.disc svg { width: 3.2cqw; height: 3.2cqw; color: var(--accent); }
.badge { position: absolute; top: -.5cqw; right: -.5cqw; width: 2.2cqw; height: 2.2cqw; border-radius: 50%; background: var(--deep); color: var(--slide); display: grid; place-items: center; font-size: 1.3cqw; font-weight: 700; font-variant-numeric: tabular-nums; }
.step h3 { font-size: 2cqw; font-weight: 700; margin: 1.1cqw 0 .35cqw; }
.step p { font-size: 1.55cqw; line-height: 1.35; color: var(--muted); margin: 0 auto; max-width: 16cqw; }
.step.final .disc { background: var(--accent); }
.step.final .disc svg { color: var(--on-accent); }
```

**Badge contrast inversion (hard rule):** on an accent-filled disc the badge inverts — light theme `background: var(--ink); color: var(--slide)`; dark theme overrides again, **in both dark blocks**, to `background: var(--bg); color: var(--ink)`. Accent-on-accent never ships.

```css
.step.final .badge { background: var(--ink); color: var(--slide); }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) .step.final .badge { background: var(--bg); color: var(--ink); }
}
:root[data-theme="dark"] .step.final .badge { background: var(--bg); color: var(--ink); }
```

Step-subline `max-width` scales with column count: ~13.5cqw at 7 cols, ~16 at 5, ~22–28 at 3.

## 3. Loopback bracket

Dashed left/right/bottom border box under a pipeline, rounded bottom corners, centered label with an opaque `--slide` background breaking the dash. Signals a step that repeats.

```html
<div class="loopback"><span>Calibration repeats at the start of each season</span></div>
```

```css
.loopback { position: relative; margin: 2cqw calc(100% / 10) 0; height: 2.8cqw; border: 2px dashed var(--line); border-top: none; border-radius: 0 0 12px 12px; }
.loopback span { position: absolute; left: 50%; bottom: -1cqw; transform: translateX(-50%); background: var(--slide); padding: 0 1cqw; font-size: 1.4cqw; color: var(--muted); white-space: nowrap; }
```

## 4. Progressive reveal

Pill ghost button (`aria-expanded` drives a chevron rotation) + hidden panel. Two-class JS animation: `.open` sets `display`, `.in` on a **double `requestAnimationFrame`** triggers the fade/slide; close is instant. `prefers-reduced-motion` neutralizes all transitions (base zone). Panels carry "why it matters" depth, never content required to understand the slide.

```html
<div class="reveal">
  <button class="reveal-btn" type="button" aria-expanded="false" aria-controls="why">Why it matters <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></button>
  <div class="reveal-panel" id="why">
    <p>Every reading flows the same way, so one glance answers what used to take a site visit.</p>
  </div>
</div>
```

```css
.reveal { margin-top: 1.6cqw; }
.reveal-btn { display: inline-flex; align-items: center; gap: .6cqw; font-size: 1.4cqw; font-weight: 600; font-family: inherit; color: var(--accent); background: transparent; border: 1px solid var(--line); border-radius: 999px; padding: .55cqw 1.4cqw; cursor: pointer; }
.reveal-btn svg { width: 1.4cqw; height: 1.4cqw; transition: transform .25s ease; }
.reveal-btn[aria-expanded="true"] svg { transform: rotate(180deg); }
.reveal-panel { display: none; opacity: 0; transform: translateY(.8cqw); transition: opacity .3s ease, transform .3s ease; margin-top: 1.2cqw; }
.reveal-panel.open { display: block; }
.reveal-panel.in { opacity: 1; transform: none; }
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

`--soft` cards, 10px radius, centered icon + heading + one-line body. Standard `1.2cqw` gap.

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
.tiles { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1.2cqw; margin-top: 2.6cqw; }
.tile { background: var(--soft); border-radius: 10px; padding: 1.6cqw 1.4cqw; text-align: center; }
.tile svg { width: 2.6cqw; height: 2.6cqw; color: var(--accent); }
.tile h3 { font-size: 1.75cqw; font-weight: 700; margin: .7cqw 0 .35cqw; }
.tile p { font-size: 1.4cqw; color: var(--muted); margin: 0; }
```

## 6. Evidence / figure strip

Row of large tabular-nums figures with captions. **Grids holding `{{TOKEN}}`s need `minmax(0, 1fr)` tracks + `overflow-wrap: anywhere`** so unfilled tokens can't blow the layout. When figures sit near a steps row, separate with a divider and an own heading so no 1:1 mapping is implied.

```html
<div class="figures">
  <div class="figure"><div class="num">14</div><div class="cap">sites live through the season</div></div>
  <div class="figure"><div class="num">{{HOURS_SAVED}}</div><div class="cap">team hours saved per week</div></div>
</div>
```

```css
.figures { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1.2cqw; margin-top: 2.6cqw; }
.figure { text-align: center; }
.figure .num { font-size: 3.4cqw; font-weight: 700; font-variant-numeric: tabular-nums; color: var(--accent); overflow-wrap: anywhere; }
.figure .cap { font-size: 1.4cqw; color: var(--muted); margin-top: .35cqw; }
```

## 7. Case cards

Half-width paired cards with bullet lists. `text-wrap: balance` on multi-line bullets; **sibling cards follow the same bullet sequence** — a change in one changes all.

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
.cases { display: grid; grid-template-columns: repeat(2, 1fr); gap: 1.2cqw; margin-top: 2.6cqw; }
.case { background: var(--soft); border-radius: 10px; padding: 1.6cqw 1.4cqw; }
.case h3 { font-size: 1.75cqw; font-weight: 700; margin: 0 0 .7cqw; }
.case ul { margin: 0; padding-left: 2cqw; }
.case li { font-size: 1.4cqw; color: var(--muted); line-height: 1.35; margin-top: .45cqw; text-wrap: balance; }
```

## 8. State cards

Equal compact cards with a count each, content vertically centered. Single numbers only.

```html
<div class="states">
  <div class="state"><div class="count">14</div><div class="label">Live</div></div>
  <div class="state"><div class="count">4</div><div class="label">Installing</div></div>
  <div class="state"><div class="count">9</div><div class="label">Scheduled</div></div>
</div>
```

```css
.states { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.2cqw; margin-top: 1.2cqw; }
.state { background: var(--soft); border-radius: 10px; padding: 1.4cqw; min-height: 8cqw; display: flex; flex-direction: column; justify-content: center; text-align: center; }
.state .count { font-size: 2.8cqw; font-weight: 700; font-variant-numeric: tabular-nums; }
.state .label { font-size: 1.4cqw; color: var(--muted); margin-top: .25cqw; }
```

## 9. Stacked rows

Full-width horizontal cards, numbered. For sequences that read top-to-bottom rather than left-to-right.

```html
<div class="rows">
  <div class="rowcard"><span class="n">1</span>
    <div><h3>Survey the site</h3><p>One visit, one checklist, photos of every mount point</p></div>
  </div>
  <!-- … more rows … -->
</div>
```

```css
.rows { display: grid; gap: 1.2cqw; margin-top: 2.6cqw; }
.rowcard { display: flex; align-items: center; gap: 1.4cqw; background: var(--soft); border-radius: 10px; padding: 1.4cqw 1.6cqw; }
.rowcard .n { width: 3.2cqw; height: 3.2cqw; border-radius: 50%; background: var(--deep); color: var(--slide); display: grid; place-items: center; font-size: 1.4cqw; font-weight: 700; font-variant-numeric: tabular-nums; flex: none; }
.rowcard h3 { font-size: 1.75cqw; font-weight: 700; margin: 0; }
.rowcard p { font-size: 1.4cqw; color: var(--muted); margin: .2cqw 0 0; }
```

## 10. Highlight band

Accent-tinted full-width band for the slide's **key evidence line**. Same internal padding as adjacent cards.

```html
<div class="band">Teams report the first useful alert within {{FIRST_ALERT_DAYS}}&nbsp;days of go-live.</div>
```

```css
.band { background: var(--soft); border-left: 4px solid var(--accent); border-radius: 10px; padding: 1.6cqw 1.4cqw; margin-top: 1.6cqw; font-size: 1.75cqw; }
```

## 11. Mini-flow

Compact centered 3-step variant of the pipeline (fixed narrow tracks, `justify-content: center`, accent arrows) for inside reveal panels.

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
.mini-flow { display: flex; justify-content: center; align-items: center; gap: 1cqw; }
.mini-step { background: var(--soft); border-radius: 8px; padding: .8cqw 1.2cqw; font-size: 1.4cqw; font-weight: 600; }
.mini-flow svg { width: 1.6cqw; height: 1.6cqw; color: var(--accent); flex: none; }
```

## 12. Footer strip

Pinned via `margin-top: auto`: **one icon + one muted sentence, identical format on every slide.** No bold, no separators beyond a middot, never time expectations.

```html
<div class="footer">
  <svg viewBox="0 0 24 24" aria-hidden="true"><!-- icon --></svg>
  <span>Fieldkit rollout · one path for every site.</span>
</div>
```

Styles are in the base zone (`.footer`).

## 13. Nav / index slide (`s00`)

Eyebrow + title + grid of link cards (number disc + name + one-line subtitle); keys 1–9 open slides.

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
.deck-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.2cqw; margin-top: 3cqw; }
.deck-card { display: flex; align-items: center; gap: 1.2cqw; background: var(--soft); border-radius: 10px; padding: 1.6cqw 1.4cqw; text-decoration: none; color: var(--ink); }
.deck-card .n { width: 3.2cqw; height: 3.2cqw; border-radius: 50%; background: var(--deep); color: var(--slide); display: grid; place-items: center; font-size: 1.4cqw; font-weight: 700; font-variant-numeric: tabular-nums; flex: none; }
.deck-card h3 { font-size: 1.75cqw; font-weight: 700; margin: 0; }
.deck-card p { font-size: 1.3cqw; color: var(--muted); margin: .25cqw 0 0; }
.deck-card:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
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
