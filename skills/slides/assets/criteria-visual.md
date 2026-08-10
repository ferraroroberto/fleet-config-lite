# slides · visual QA criteria (hard gates)

Checked on **every** slide, in **both themes**, with **reveals expanded** — rendered in Chrome and measured programmatically, never eyeballed. **Fixing by shrinking fonts is banned:** rewrite copy or rebalance layout instead.

1. **Sibling balance** — cards/tiles in a row carry comparable text volume.
2. **No orphan last lines** — restructure into two deliberate balanced lines.
3. **Uniform line rhythm** — identical spacing whether a break is a wrap or explicit.
4. **Vertical centering** — card content optically centered, equal space above and below.
5. **Homogeneous page fill** — no bottom crowding, no dead band above the footer, expanded states included. Dead space above the footer targets ~10cqw.
6. **Badge contrast** — the inversion rule from the component catalog; accent-on-accent never ships.
7. **Uniform footer** — icon + one muted sentence, no bold, no separators, and **never time expectations** ("45 min", "Demo · 15 min") — the presenter manages time off-slide.
8. **No implied mappings** — never N figures directly under N unrelated steps; a divider plus an own heading breaks the false 1:1.
9. **No em dashes** in copy or titles — commas, or a period when a comma would stack; `<title>` tags separate with a middot.
10. **Audience vocabulary** — no internal jargon; no presenter mechanics (shortcuts, timings, F-keys) visible anywhere.
11. **Uniform gaps/padding** — 1.2cqw card gap deck-wide; band padding matches adjacent cards.
12. **Parallel sibling structure** — comparable cards follow the same bullet sequence; a change in one changes all.

## Build lessons baked in

- Step-subline `max-width` scales with column count: ~13.5cqw at 7 cols, ~16 at 5, ~22–28 at 3.
- Sparse slides may scale type up; dense slides keep contract sizes.
- Sparse slides can also rebalance instead: give the main content block `margin-top: auto` so the leftover space splits evenly with the footer's own auto margin (the examples' `s01` pipeline does this), rather than leaving one dead band above the footer.
- `&nbsp;` between digits and their nouns so numbers never separate from what they count.
- Fill-in guidance for `{{TOKEN}}`s: outcome lines ≤2 wrapped lines, cost strings ≤14 chars, single numbers in state cards.

## How to verify

Render each slide file in Chrome at a 16:9 viewport (e.g. 1600×900), in light and dark, reveals expanded, and measure: the `.slide` box must be exactly 16:9; `scrollHeight`/`scrollWidth` of the frame must not exceed its client box (the fit contract); zero non-`file://` network requests; toggle, reveal and keyboard nav must actually work. A slide that fails any measure goes back for a copy rewrite or layout rebalance, not a font shrink.
