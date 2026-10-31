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
   - **easy** → run this repo's `/issue-yolo <N>` end-to-end (branch, build, gate, `/e2e`, MR, merge, land), with the **ship override** below.
   - **hard** → run `/issue-start <N> now`, build, run the verification gate, then **stop before push** and hand back a plain-English summary of what changed and why, plus the ship override below for the human to apply when running `/issue-finish`.

   **Ship override (both paths).** `/issue-yolo` and `/issue-finish` default to `Closes #<N>`, which would auto-close the audit issue on merge and drop every unfixed item from the backlog (the next audit only reuses *open* managed issues). So:

   - The MR description says `Closes #<N>` only when every `- [ ]` item is fixed by this MR; otherwise it says `Part of #<N>`. (`audit_gate.py` still skips the commit, since any `#N` of an audit issue counts as a reference.)
   - After the merge, tick the fixed items: fetch the body with `audit_gate.py get`, change `- [ ]` to `- [x]` on exactly the fixed items, and write it back with `audit_gate.py upsert --kind <bucket> --label <bucket> --title "audit: <bucket> findings" --body-file <tmp>` (works on GitHub and GitLab; an MR cannot edit an issue body). Skip this when `Closes #<N>` already closed the issue.
6. **Report** what merged, what is waiting for review, what was deferred.

## Hard rules

- One repo at a time, never two branches in one checkout.
- Never close an audit issue by hand, and never tick an item this run did not fix and merge; the checklist is a living backlog. Ticking goes only through the post-merge `audit_gate.py upsert` step, and closing only through `Closes #<N>` on an MR that fixes the last unticked item.
- Never widen scope past the checklist items: an unrelated bug found on the way gets its own issue via `/issue-add`.
- A red gate stops that repo's work and is reported; the loop moves on.
