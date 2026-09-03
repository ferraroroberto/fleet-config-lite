---
name: codebase-audit
description: Audit a repo's resting-state quality against its instructions file and senior-dev standards — bugs, stale/dead code, slop, doc drift — into at most four living-backlog issues, gated so an unchanged repo is never re-read. E.g. "/codebase-audit", "/codebase-audit src/", "audit the codebase", "find dead code and slop".
---

# codebase-audit (lite, host-agnostic)

**Goal:** read the codebase (or one subtree) the way a senior, perfectionist
developer would and surface the resting-state rot that diff-scoped reviews
never see — into **at most four issues per repo, ever**, one living backlog
per bucket, reused across runs. Issues, never code edits: filing is the only
side effect.

Downscaled from the private `fleet-config` skill for a limited-credit
environment: four buckets instead of seven, a hard cap on findings per run,
no security self-heal, no Slack, no schedulers. The one deterministic piece
is vendored beside this file: `audit_gate.py` (stdlib only, `gh` or `glab`
picked from the repo's `origin`). Run it from **this skill's base directory**
with Python ≥3.11; the GitLab path follows `glab`'s documented shape but is
not live-tested.

**The gate is the point.** A repo is re-read only when organic source change
since the last audit crosses a threshold (default 1000 added+deleted lines;
docs, markdown, tests and lockfiles weigh nothing; commits that reference the
repo's own audit issues are self-fixes and weigh nothing). Below it, the
repo accumulates quietly and the run stops before reading a file. This is
what stops the audit → fix → re-audit loop that keeps re-finding marginal
things and turns the fixes into new slop.

## Arguments

- Nothing → whole repo.
- One path → scope the *read* to that subtree; the rubric is still read whole. A scoped run never reads or writes the ledger (steps 2 and 8).
- `threshold=N` → override the significance threshold for this run.

## The four buckets

1. **bug** — a correctness issue you would bet money on: wrong default, off-by-one, missing guard on a reachable path. Speculation goes nowhere.
2. **stale** — dead code: an orphaned module no caller references, a removed feature's scaffolding still wired in, references to things that no longer exist.
3. **slop** — volume or structure that does not earn its keep: duplicated logic, a 40-line hand-rolled version of a stdlib one-liner, an abstraction with one caller, defensive arms for inputs that cannot occur, a god-module mixing unrelated concerns.
4. **documentation** — README/docs that document a removed feature, contradict the code (port, command, config key), duplicate each other and diverge, or miss a headline user-facing surface entirely.

A violation of the project's instructions file goes in whichever bucket its subject belongs to, citing the rule. A **security** finding (injection sink, committed secret, missing authz) is never written to an issue: report it to the terminal only, `file:line` plus one sentence, and let the human handle it.

## Steps

1. **Pre-flight.** `git rev-parse --show-toplevel` (else stop: not a git repo) and `git remote get-url origin` (else stop: this skill files issues). Working tree must be on the default branch and clean for a whole-repo run.
2. **Gate** (whole-repo runs only): `python <base-dir>/audit_gate.py --repo-path <root> gate [--threshold N]`. Read the JSON `decision`. Any `SKIP*` → print the `reason`, `significance`/`threshold` when present, and **stop without reading a single file**. `SKIP_SELF_FIX` has already advanced the ledger. Only `AUDIT` continues.
3. **Rubric.** Read the project instructions file — first of `CLAUDE.md`, `AGENTS.md`, `copilot-instructions.md`, `.github/copilot-instructions.md` (the same order `audit_gate.py` hashes) — and the user-level instructions if present. Extract the specific, checkable rules.
4. **Inventory.** `git ls-files [<path>]`, keeping source files plus `README.md` and `docs/`. Skip generated code, lockfiles, vendored trees, assets. Above ~150 files, prioritise entry points, files touched in the last three months (`git log --since="3 months ago" --name-only`), and anything the rubric names — and say so in the report.
5. **Read and note.** Per finding: bucket, `file:line`, one sentence on what is wrong, one sentence on the fix shape. **Cap: 5 new findings per bucket per run.** Apply the materiality bar to each one: would a senior developer agree this is worth a future developer's time? Hesitate → drop it. Empty buckets are the right answer for a healthy repo.
6. **Dedupe.** Fetch open issues (`gh issue list --state open` / `glab issue list`). A finding already covered by an issue that is *not* this bucket's managed issue is dropped and listed as `skipped: dupe of #N`.
7. **Upsert one issue per non-empty bucket.** For each: `python <base-dir>/audit_gate.py --repo-path <root> get --kind <bucket>`. If `number` is null, write a fresh body (below). Otherwise **merge** into the returned body: keep every `- [x]` verbatim, match existing items by file path (update the line number, keep the checkbox), append new items, and tag items not re-surfaced this run inline as `_(carried — not re-verified since <date>)_`. Never tick, close, or `Closes #` — closing is the human's call once every box is checked. Append `<YYYY-MM-DD> @ <short-sha>: +A new, B carried` to the run log. Then `python <base-dir>/audit_gate.py --repo-path <root> upsert --kind <bucket> --label <bucket> --title "audit: <bucket> findings" --body-file <tmp>`. Body paragraphs are single lines (rendered markdown).

   ```markdown
   Surfaced by `/codebase-audit`, kept up to date across runs. Scope: <whole repo | path>.

   ## Findings

   - [ ] **<file>:<line>** — <what's wrong>. Fix: <fix shape>.

   ## Context

   <One short paragraph: the common thread, why these matter together, what the next `/issue-start` should know.>

   ## Audit run log

   - <YYYY-MM-DD> @ <short-sha>: initial.
   ```

8. **Ledger** (whole-repo runs only, every non-skipped run including a clean one): `python <base-dir>/audit_gate.py --repo-path <root> ledger-write`. It records the default-branch sha (never a feature-branch tip), today's date and the rubric hash. If it exits non-zero, leave the ledger alone and say so.
9. **Report** one table and stop:

   ```
   /codebase-audit — <owner/repo>  (scope: <whole repo | path>)
     bucket          findings  new  carried  issue
     bug                    0    0        0  (none)
     stale                  2    2        0  <url>
     slop                   3    1        2  <url>
     documentation          1    1        0  <url>
     security: none | <file:line — one sentence> (terminal only, not filed)
     skipped as duplicates: <file:line — dupe of #N> | none
     files inspected: <n> (prioritisation: <none | recent + entry points>)
   ```

   All buckets empty → `No actionable findings. Codebase passes the audit.`

## Hard rules

- Never edit, commit, push or restart anything. Issues are the only output.
- Never `gh issue create` a managed issue by hand — `audit_gate.py upsert` owns identity so a re-run can never spawn a duplicate.
- Never write the ledger block yourself — `ledger-write` owns the format (shared with the private fleet tool, so a repo audited by both keeps one ledger).
- Citations or it did not happen: every finding names a real `file:line`.
- Fewer is better. Do not file to look thorough; five per bucket is a ceiling, not a target.
- Security findings stay in the terminal. No issue, no commit, no comment.
