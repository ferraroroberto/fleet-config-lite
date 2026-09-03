---
name: audit-fleet
description: Run the gated /codebase-audit across every sibling repo next to this one, sequentially and capped per run, printing one plan and one summary table. E.g. "/audit-fleet", "/audit-fleet 1", "/audit-fleet E:\work", "audit all my repos".
---

# audit-fleet (lite, sequential)

**Goal:** the cheap enumerate-and-gate loop around `/codebase-audit`. Walk
every repo beside this one, ask `audit_gate.py` which ones actually changed
enough to deserve a read, and audit **only those, one at a time, at most N per
run**. The gate makes most repos free; the cap bounds what a single run can
cost in credits.

The orchestrator files nothing itself: the only writes are the issues and
ledgers each `/codebase-audit` run upserts. No sub-agents, no scheduler, no
digest issue, no notifications — the summary table on stdout is the digest.

## Arguments

Order-independent, all optional:

- A directory → the fleet root. Default: the parent directory of the current repo.
- An integer → max repos to audit this run. Default `2`.
- `threshold=N` → passed through to every gate call.

## Steps

1. **Enumerate.** Every direct child of the root that has a `.git` and an `origin` remote. Skip, and report, any checkout that is dirty or not on its default branch — never stash, never switch branches.
2. **Sync.** In each candidate: `git pull --ff-only` (a failure skips the repo with its reason).
3. **Gate.** `python <codebase-audit base-dir>/audit_gate.py --repo-path <repo> gate [--threshold N]` per repo, and print one plan table before reading anything:

   ```
   /audit-fleet plan — root <dir>
     repo              decision              commits  significance/threshold
     app-a             AUDIT                      14  1840/1000
     app-b             SKIP_BELOW_THRESHOLD        3   210/1000
     app-c             SKIP                        0   -
     app-d             AUDIT (no-ledger)           -   -
     skipped: app-e (dirty), app-f (on feat/12-x)
   ```

4. **Audit.** For the `AUDIT` rows, in the table's order, up to the cap: change into that repo and follow `/codebase-audit`'s steps 3–9 to completion before starting the next. Rows past the cap are listed as `deferred — next run`; the gate will still say `AUDIT` for them then, nothing is lost.
5. **Summary.** One table: repo, findings per bucket, issues touched, security count (terminal only). Deferred and skipped repos listed underneath.

## Hard rules

- Sequential, always. Never audit two repos at once.
- Never raise the cap on your own to "finish the fleet" — the cap is the credit budget.
- A repo that fails mid-audit is reported and the loop continues; only a missing root or a missing `gh`/`glab` stops the run.
