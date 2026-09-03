---
name: cleanup-fleet
description: Fix one bucket of /codebase-audit findings (bug, stale, slop or documentation) across the sibling repos, one repo per run by default, delegating each issue to /issue-yolo or a build-and-stop /issue-start. E.g. "/cleanup-fleet documentation", "/cleanup-fleet slop 2", "clean up the stale code".
---

# cleanup-fleet (lite, one repo at a time)

**Goal:** the fix half of `/audit-fleet`. Pick one bucket, find each sibling
repo's managed `audit: <bucket> findings` issue, and work it through the
skills this repo already ships — nothing here reinvents the branch → gate →
MR flow. Bounded by design: one repo per run unless told otherwise, so a run
costs one issue's worth of credits, not a fleet's.

## Arguments

`/cleanup-fleet <bucket> [max] [<root>]`

- **bucket** (required): `bug` | `stale` | `slop` | `documentation`. Synonyms: `bugs`, `dead`/`dead-code` → `stale`, `bloat`/`dup`/`duplication` → `slop`, `docs`/`doc` → `documentation`.
- **max**: repos to work this run. Default `1`.
- **root**: fleet root. Default: the parent directory of the current repo.

## Steps

1. **Enumerate** like `/audit-fleet` step 1: sibling repos with `.git` + `origin`; skip dirty or off-default checkouts.
2. **Find the issue** per repo: `python <codebase-audit base-dir>/audit_gate.py --repo-path <repo> get --kind <bucket>`. `number: null` → nothing to do there. Read the body; count unticked `- [ ]` items.
3. **Score** each candidate issue: **easy** = mechanical, narrow, clear acceptance (doc fixes, a few dead-code deletions, a rename); **hard** = a design choice, multi-module, a refactor, or a mixed checklist. On the fence → hard.
4. **Plan** and print it before any write:

   ```
   /cleanup-fleet <bucket> — max <n>
     repo      #    open items  tier   path
     app-a     31   4           easy   /issue-yolo → merged
     app-b     12   9           hard   /issue-start now → build → stop for review
     deferred (past cap): app-c#8
   ```

5. **Work** the first `max` rows, sequentially, inside each repo:
   - **easy** → run this repo's `/issue-yolo <N>` end-to-end (branch, build, gate, `/e2e`, MR, merge, land). The MR ticks the boxes it fixed in the issue body; it never closes the issue with `Closes #N` unless every box is now ticked.
   - **hard** → run `/issue-start <N> now`, build, run the verification gate, then **stop before push** and hand back a plain-English summary of what changed and why, for the human to ship with `/issue-finish`.
6. **Report** what merged, what is waiting for review, what was deferred.

## Hard rules

- One repo at a time, never two branches in one checkout.
- Never tick or close an audit issue by hand; the checklist is a living backlog and the MR is what ticks it.
- Never widen scope past the checklist items: an unrelated bug found on the way gets its own issue via `/issue-add`.
- A red gate stops that repo's work and is reported; the loop moves on.
