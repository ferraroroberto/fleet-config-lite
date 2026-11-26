---
name: slides
description: Two-phase HTML presentation builder that replaces PowerPoint. Phase 1 turns a voice dump or rough structure into a closed briefing (audience, message, sequence, one idea per slide) and refuses to build until it is closed; Phase 2 composes self-contained 16:9 HTML slides from a standard component catalog, verifies every slide in Chrome (both themes, reveals expanded, measured, never eyeballed), and uses deterministic scripts for style propagation and print/PDF export. Invoke with "build a deck", "prepare slides for …", "new presentation from this dump", "brief me a deck", "export the deck to PDF", or "change the deck's brand color".
---

# slides

**Goal:** Turn a rough brief into a verified, self-contained HTML slide deck — composed from a standard component catalog, styled from a single brand-color source, presentable from any browser with zero external requests.

Everything this skill needs ships in this folder (`assets/` + `scripts/`) plus the sibling `skills/_lib/` (`runtime_files.py`, imported by every script here that writes into a deck; `lint_deck.py` also imports `git_run.py` and `no_window.py`); it has no dependency on any other repo or checkout. All file references below are **relative to this skill's base directory** (shown when the skill loads); the scripts are stdlib-only, any Python ≥3.11 works.

**Do not load the `assets/` files up front** — they are read at the point Phase 2 needs them (lean-context rule); the briefing phase doesn't need them at all.

Per-client brand tokens and standing deck preferences are **private and never live in this skill's folder or any tracked repo** — they live in an untracked location of the user's choosing. If the user has a brand-tokens file for this client, ask them to point to it (or paste the values); no values yet → the placeholder green tokens stay until the user provides real ones.

## Operating instructions — two phases, one gate

### Phase 1 — briefing (the clarity gate)

Input: a voice/audio dump, a pasted outline, or a rough structure. Your job here is **clarity, not slides**:

1. Extract what is already answered: what to communicate, to whom, in what sequence.
2. Ask the clarifying questions the dump leaves open — audience and what they already know, the single message, the slide sequence, **one idea per slide** (a slide with two ideas becomes two slides), which figures are verified vs. pending.
3. **Refuse to build until the briefing is closed.** "Just make something" is not a closed briefing; say what is still open and why it blocks.
4. Output: a **briefing/handoff document** with, per slide — working title, the one message, the copy (or copy direction), the one component that will carry it (picked from the chooser table in `assets/components.md`, besides the header and footer every slide takes), and `{{TOKEN}}` placeholders for every figure not yet verified, plus a fill-in inventory table (token · slide · what fills it · who confirms it).
5. **Bilingual:** the briefing's language (ES/EN) drives the deck's language. The skill's machinery — file names, anchors, class names — stays English.

The gate: Phase 2 starts only when the user approves the briefing. That approval is the plan gate for the deck.

### Phase 2 — build

Read the assets **now, at the point of use** — never inline them into memory of this prompt:

- `Read` `assets/design-system.md` — the normative visual contract.
- `Read` `assets/components.md` — the component catalog; compose slides **only** from these pieces, choosing each from its chooser table and use-when / don't-use-when rules.
- `Read` `assets/criteria-content.md` and `assets/criteria-visual.md` — the copy rules and the hard visual gates.
- Copy `assets/template.html` as the canonical starting point for every slide; take icon path data from `assets/icons.html` (hand-drawn SVG is banned; a missing glyph gets added to the gallery from Lucide first).
- The composed examples in `assets/examples/` show what good output looks like.

Build in four rounds, in this order:

1. **Catalog only.** Each slide gets the component the briefing picked for it, and its CSS is catalog blocks only. The lint (under Verification) must exit 0 or 1 before you ask for review.
2. **Propose, then build locally.** Once the catalog-only build exists, review the deck and propose changes as text ("slide 4 reads better as a variant of state cards"). Build only what the user OKs, each as a deck-local block (build rule 6) whose line names its purpose and the catalog id it extends. A deck session never edits this skill's files.
3. **Component request.** When the user approves the final look, run `python <skill-dir>/scripts/component_request.py <deck-dir>`: it writes `component-request-<name>.md` beside the deck for each local block, from the slide's structure and the CSS, with no slide copy. Fill its two `TODO` lines in general terms (no client copy, brand values, names or figures), then run it with `--check` until it exits 0. The check is a screen, so the user reads each request and files it as an issue in this skill's repo; you file one only on their OK.
4. **Re-base.** After the request is merged into the catalog, update the skill, then in a new session run `python <skill-dir>/scripts/lint_deck.py <deck-dir> --session-start` and `python <skill-dir>/scripts/rebase_deck.py <deck-dir>`. It swaps each local block for the catalog block of the same name, or refuses and writes nothing; the lint then exits 0 and the deck is final.

A request keeps its block's name when the catalog takes it (`<extends>.<name>` for a variant, `<name>` for a new component), because re-basing matches by name.

Build rules:

1. **Multi-file model:** one HTML file per slide (`s01-<slug>.html` …) plus an `s00-nav.html` index. **Ask the user for a target deck folder outside any tracked repo** if not stated. **Client decks never land in a tracked path.**
2. **Per-deck localStorage key:** replace `<deck-key>` with the deck's slug in every file, identical across the deck.
3. **Minimal-LLM principle (hard):** you write content and per-slide layout. Everything mechanical is a script's job — a token or shared-CSS change is edited **once** and fanned out with `python <skill-dir>/scripts/propagate.py <edited-slide> <deck-dir>`; print/PDF export is `python <skill-dir>/scripts/make_print.py <deck-dir> [--pdf]`. **Never hand-edit ten files for a CSS change.** The `==slides:*==` anchors are load-bearing; never strip them.
4. **Catalog blocks verbatim:** each component's CSS goes into the per-slide zone exactly as `components.md` gives it, inside its `==slides:c:<id>[.<variant>]@<version>==` anchors, which declare the catalog pieces a slide uses; `assets/catalog.json` holds each block's hash. Per-slide settings go through the component's knobs (custom properties in a `style` attribute), never through edits inside a block. A catalog change edits `components.md`, bumps the component's version and regenerates the index with `python <skill-dir>/scripts/build_catalog.py`.
5. **Real brand colors** come from the user's private brand-tokens source and are stamped by editing `--brand`/`--brand-dark` in one slide, then propagating. The tracked placeholder green must never survive into a client deck, and client hex values must never be written into any tracked file.
6. **Catalog only, checked by a script.** Once the deck folder exists, record the skill's state with `python <skill-dir>/scripts/lint_deck.py <deck-dir> --session-start`; a deck session never edits this skill's files, and the lint fails if `assets/` changed since. Any CSS a slide needs beyond the catalog goes, only with the user's OK, in a deck-local block: `/* ==slides:local:<name>== */`, first line `/* purpose: <one line> · extends: <catalog id|none> */`, closed by `/* ==/slides:local:<name>== */`. Every other rule, an edited catalog block, a changed `base` zone, a `tokens` change beyond `--brand`/`--brand-dark`, or a `style` attribute that sets more than custom properties is ad-hoc CSS.

### Verification (mandatory, never eyeballed)

Run `python <skill-dir>/scripts/lint_deck.py <deck-dir>` first. Exit 0 = catalog only; 1 = draft (deck-local blocks); 2 = ad-hoc CSS or a changed skill folder, which is fixed before anything else; 3 = it could not check, which is never read as clean. **A deck is called final only when the lint exits 0.** Exit 1 is reviewable as a draft. For an older deck full of one-off CSS, `lint_deck.py <deck-dir> --inventory` writes `lint-inventory.md` beside the deck (refused inside a tracked folder): the unanchored rules grouped by the classes they style, each group with its likely catalog match, near match (a candidate variant) or no match (a candidate new component).

Then render **every** slide in Chrome at a 16:9 viewport, **both themes, reveals expanded**, and measure programmatically: exact 16:9 frame, no overflow beyond the frame (the "must fit, never scroll" contract), zero non-`file://` requests, toggle + reveal + nav working. Apply every gate in `criteria-visual.md`; a failing slide gets a copy rewrite or layout rebalance, **never** a font shrink. Then run `make_print.py` and check `print.html`: one slide per page, reveals expanded, light theme.
