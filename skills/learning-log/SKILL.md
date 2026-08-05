---
name: learning-log
description: Weekly-shaped learning log + forward horizon + productivity stats distilled from this repo's sibling-repo work stream (merged PRs/MRs and closed issues, no source code). Host-agnostic (GitHub or GitLab, whichever this repo's origin uses). Use when the user wants the learning journey and productivity distilled — e.g. "/learning-log", "learning log", "what did we ship and learn recently". Manual invoke only, no scheduler.
---

# learning-log (lite, host-agnostic)

**Goal:** Surface the *learning journey* and *productivity shape* otherwise
buried inside individual PRs/MRs and issues. On invocation, read the **work
stream itself** — every merged PR/MR and closed issue across this repo and
its siblings (other repos under the same owner/group, on whichever host this
repo lives on) since the last run — then (a) compute **exact productivity
tables** (PRs/MRs, issues, LOC, by repo and by work-type) and (b) fan out
**one insight sub-agent per work-type bucket** to extract patterns, recurring
root-causes, and durable lessons. Aggregate into a themed log, **grade the
last horizon**, and set the next one.

Ported from the private `fleet-config`'s `.claude/skills/learning-log`
(per this repo's own README: "when a capability is missing here, port it
from there deliberately rather than re-inventing it"), but reshaped to fit
this repo's principles rather than copied verbatim:

- **No scheduler.** The source skill runs unattended on a weekly Windows Task
  Scheduler job (`run-weekly.bat` + an app-launcher Job). This repo's README
  states "no schedulers" — this port is **manual-invoke only**. There is no
  `run-weekly.bat`, no wiring section, no unattended entry point.
- **Model-agnostic insight step, not "no LLM calls".** fleet-config's
  version hardcodes Sonnet sub-agents. That's a genuine, narrow carve-out
  from this repo's stated "no LLM calls" principle — accepted deliberately
  for this one skill, on the condition that the insight step never
  hardcodes a vendor/model name: it uses whichever model/agent is already
  running this session, at low reasoning effort (this step extracts
  patterns from a short bucket file, not deep work). See step 2.
- **Host-agnostic, not GitHub-only.** fleet-config's version is hardcoded to
  `gh`/GitHub. This repo's other skills (`issue-add`, `issue-start`,
  `issue-finish`) target GitLab via `glab`. This port detects which host the
  *current* repo's `origin` remote points at and drives the matching CLI —
  gathering from siblings on that same host, under the same owner/group.
- **No external helper dependency.** fleet-config's version calls out to
  `C:/Users/rober/.claude/skills/_lib/audit_issue.py`, `no_window.py`,
  `claude_progress.py`, and `hooks/notify_complete.py` — none of which exist
  in fleet-config-lite. This port's `gather.py` is fully self-contained
  (stdlib + `gh`/`glab` only) and owns its own ledger upsert + comment logic.
- **No Slack ping.** fleet-config-lite has no notification helper; the final
  report (step 5) is the only output.

**Verified vs. assumed:** this repo's own `origin` is GitHub, and `gh` is
what's actually installed on the machine this was built on — the GitHub path
in `gather.py` is exercised live (read-only) against this repo. The GitLab
path is written to `glab`'s documented CLI shape but is **not** live-tested
here (`glab` isn't installed on this dev machine) — the same caveat already
applies to this repo's other `glab`-based skills. GitLab's MR/issue list API
also doesn't expose per-item diff stats the way GitHub's does, so
additions/deletions stay `0` on the GitLab path — a known fidelity gap, not
a bug.

## Arguments

- No argument → auto window (since the ledger's `last-run-at`, or trailing 7
  days on the first run).
- `since <YYYY-MM-DD>` → override the window start (first backfill /
  validation, e.g. `since 2026-05-01`).

## Execution rules (read first)

- **Run from this skill's base directory** (shown when the skill loads) so
  `gather.py` resolves relative to itself.
- **Public repos only.** `gather.py` always includes the current repo
  itself, plus **public** sibling repos on the same host/owner — private
  siblings are never gathered, counted, or narrated, since the ledger issue
  this run writes to may itself be public even when a sibling isn't.
- **Read-only except two writes:** the ledger issue (upsert) and the weekly
  comment on it. Never edits source, commits, pushes, or restarts anything.
- **Stats are deterministic — never let the model invent numbers.** Every
  count and LOC figure comes from `gather.py` (Python over `gh`/`glab`
  JSON), pasted verbatim. The sub-agents narrate *insight*, not statistics.
- **Sub-agents are read-only analysts** — they file nothing and change no
  state; the orchestrator alone writes the ledger and comment.
- **Degrade gracefully.** A bucket sub-agent that errors is recorded as such
  and skipped; the run still produces a log. A quiet window (no PRs/MRs or
  issues) still records the run so the ledger keeps cadence.
- **No AI attribution; no hard-wrapped paragraphs** in anything posted to
  GitHub/GitLab (global `CLAUDE.md`).

## Steps

### 1. Gather + stat the work stream

```
python skills/learning-log/gather.py probe                              # sanity check: HOST/OWNER/REPO_FULL
python skills/learning-log/gather.py gather                              # auto window
python skills/learning-log/gather.py gather --since 2026-05-01           # override (backfill/validation)
```

`gather.py` detects the host (GitHub vs GitLab) from `git remote get-url
origin`, lists public sibling repos under the same owner/group, reads each
repo's merged PRs/MRs + closed issues since the window start, buckets each
item by work type, computes exact productivity stats, and writes into
`<OUT_DIR>`: `stats.md` (the productivity tables), `prior-horizon.md`, and
one `bucket-<slug>.md` per non-empty bucket. It prints a **manifest** —
capture every line:

- `HOST=` / `REPO_FULL=` — the detected host and owner/repo.
- `SINCE=` / `TOTALS=` — window start and grand totals.
- `STATS_FILE=` — the productivity tables (paste verbatim into the digest).
- `PRIOR_HORIZON_FILE=` — the prior horizon (grade against it).
- `OUT_DIR=` and one `BUCKET=<slug>|<name>|prs=N|issues=M|file=<path>` per
  non-empty bucket — dispatch one sub-agent per line.

### 2. Scatter — one insight sub-agent per bucket

For each `BUCKET=` line, dispatch a sub-agent using **this session's own
default model** — never hardcode a specific vendor/model name — and the
**lowest reasoning-effort tier available** (e.g. Claude Code: omit any
`model`/`effort` override on the `Agent` tool call so it inherits the
session default, or pick the fastest available subagent if the harness
exposes one; Copilot CLI / other agents: use whatever their own default
model is). This step reads one short bucket file and extracts patterns — it
does not need deep reasoning, and keeping it model-agnostic is what makes
this skill portable across whichever CLI/agent runs it. Each sub-agent reads
only its `bucket-<slug>.md` and extracts insight in this exact format (so
the aggregate is uniform):

```
### <Bucket name>
**Themes:** 2-4 short labels.
**Insights & learnings:**
- <durable, non-obvious lesson or recurring pattern -- not a restatement of one PR/issue title> (repo#N)
- ... (3-6 bullets)
**Notable:**
- <1-3 most significant items and why> (repo#N)
**Focus signal:** <one line -- what this bucket says about where effort/attention went>
```

Tell each sub-agent: read-only (file nothing, change no state); cite
evidence as `repo#N`; be concrete to these specific repos. Collect each
report as it returns. If a project's environment can't run background
sub-agents at all, read each `bucket-<slug>.md` directly and write these
sections yourself, in the same format.

### 3. Aggregate into the digest

Compose the digest as markdown (single long lines, no hard wraps). Order:

- `# Learning log -- <SINCE> -> today` + a one-line subtitle with the grand
  totals.
- `## TL;DR` — 3-5 phone bullets synthesizing the biggest cross-bucket
  signals.
- `## What shipped & what we learned` — the per-bucket sections from the
  sub-agents, in `BUCKET=` order, verbatim (lightly normalized).
- `## Discoveries to archive` — 4-8 durable, dated-worthy bullets pulled
  from across the buckets, each tagged `repo#N`.
- `## Horizon grading` — grade ONLY the items in `prior-horizon.md`
  (shipped / slipped) + what emerged UNPLANNED. If it says first run, write
  `First run -- baseline, no prior horizon to grade.`
- `## Horizon -> next` — 4-8 forward checkboxes inferred from open threads
  and direction of travel.
- The contents of `STATS_FILE` pasted verbatim (the productivity tables).

### 4. Assemble the ledger body + upsert

Write the new horizon bullets to `horizon.md` and the discovery bullets to
`discoveries.md` (in `OUT_DIR`), then let Python preserve the durable
archive + stamp `last-run-at`:

```
python skills/learning-log/gather.py assemble-ledger \
  --horizon-file <OUT_DIR>/horizon.md --discoveries-file <OUT_DIR>/discoveries.md \
  --out <OUT_DIR>/ledger-body.md
```

Then upsert the one canonical ledger issue (found/created by the fixed
`learning-log` label, title "Learning log"; the label is created on the
target repo if it doesn't exist yet):

```
python skills/learning-log/gather.py upsert-ledger --body-file <OUT_DIR>/ledger-body.md
```

Capture `LEDGER_NUMBER` / `LEDGER_URL`. Post the digest as a comment (the
running record):

```
python skills/learning-log/gather.py comment --issue <LEDGER_NUMBER> --body-file <digest file>
```

Capture `COMMENT_URL`.

### 5. Report

A few lines: window, grand totals, buckets analysed (+ any sub-agent that
errored), ledger + comment URLs.

## Notes

- **Why deterministic stats + sub-agent insight (not sub-agent stats):**
  counts and LOC must be exact and reproducible, so Python computes them
  from `gh`/`glab` JSON; the sub-agents do the *judgement* (patterns,
  lessons) that a table can't capture.
- **Why a ledger issue, not a `docs/` file:** durable knowledge lives in one
  canonical issue with a dated decision log, per this fleet's convention.
  The issue body is the deduped durable archive + live horizon; its
  comments are the run-by-run record (narrative + tables).
- **Why anchor the window to `last-run-at`:** a missed/late run never drops
  a period — the next run widens. First run with no ledger falls back to
  trailing 7 days.
- **Buckets** are by work type — PRs/MRs by conventional-commit prefix
  (`feat`/`fix`/`chore`/`docs`/`refactor`/...), issues by type label. Items
  with neither land in **Other**.
- **This is a narrower scope than the source skill on purpose** — no
  cross-fleet architecture map cross-link (no `/system-map` equivalent
  here), no Slack ping, no scheduler. If any of those become genuinely
  needed later, add them deliberately rather than re-inflating this skill
  back toward its fleet-config original.
