---
name: prompt-audit
description: Audits instruction files (CLAUDE.md, AGENTS.md, copilot-instructions.md, global-instructions.md, SKILL.md) in this repo and at most two sibling repos per run against the vendors' current prompting guides, then posts one ledger digest. Manual invoke only. E.g. "/prompt-audit", "/prompt-audit --dry-run", "audit our prompts against the latest guidance".
---

# prompt-audit (lite, host-agnostic)

**Goal:** keep the instruction files agents read in step with what the vendors' *current* prompting guidance says, and notice when that guidance itself moves. Three phases, in order: a **freshness gate** (did any guide change since `sources.toml`'s baselines?), a **scan** (deterministic lint plus a judgment pass against `rules.md`), and **one output** (the `prompt-audit ledger` issue body plus one digest comment on it).

**Scope.** The deliverable is the digest comment. Out of scope: editing any instruction file, committing, opening an MR/PR, filing per-repo cleanup issues, and changing the rule-set (it is owned upstream, see Notes). A finding is a report for a human to act on through the normal issue workflow.

Ported from the private `fleet-config` `/prompt-audit` and downscaled for a limited-credit setup. The caps below are enforced by `audit.py`, not only stated here:

- **At most 2 repos per run.** `plan` picks them (or refuses more than two `--repo`); `digest` and `ledger-write` refuse a run file covering more. The remaining repos are listed as deferred and come up on later runs, because files judged this run are recorded and skipped next time.
- **At most 5 findings per file per run**, violations first; the overflow is counted in the digest.
- **No sub-agents.** The judgment pass runs serially in the invoking session, one file at a time.
- **No scheduler, no chat notification.** Manual invoke only; the digest comment is the only thing posted.

Files in this directory:

- `rules.md` — the rule-set (`R-NN` blocks: tags, detect, why, fix shape, source). Its normalised sha256 is the ledger's `rubric-sha`.
- `sources.toml` — one block per vendor page with its baseline sha and marker, plus the audience vocabulary that decides which rules are primary for a file.
- `audit.py` — every exact step: `host`, `sources`, `diff-source`, `plan`, `digest`, `ledger-write`, `comment`. Stdlib only, Python 3.11+, `gh` or `glab` picked from the home repo's `origin`.

`<py>` below is the Python 3.11+ interpreter; `<audit>` is `<base-dir>/audit.py`, where `<base-dir>` is this skill's directory as shown when the skill loads.

## Arguments

- `--dry-run` — run every phase and print the plan, the judgments, the digest and the ledger body, but write nothing: `ledger-write --dry-run` prints the `ARGV=` it would run and spawns no write; no comment is posted. Reading the ledger is allowed.
- `--repo <name>` (up to two) — audit exactly these sibling repos (directory names beside this checkout). Without it, `plan` takes the first two repos in audit order that have anything to scan: this repo, then `project-scaffolding` if present, then the rest alphabetically.
- `--rescan-all` — ignore skip-unchanged for the selected repos.

## Execution rules

- **Writes are exactly two:** the ledger issue body (through `audit.py ledger-write`, which owns the marker and the hidden block) and one digest comment (through `audit.py comment`). Both land on this checkout's own `origin`. Nothing else, and none of it under `--dry-run`. Create ledger issues only through `ledger-write`, so a rerun can never spawn a second one.
- **Scratch files** (fetched pages, `run.json`, `digest.md`) go in a new, uniquely named directory in the session's temp area; a new directory per run needs no cleanup.
- **Unknown is never a pass.** A page that could not be fetched is `not-checked`, never `unchanged`. A planned file without a judgment is `unmeasured`, never compliant. A skipped file is listed as skipped.
- **Numbers come from `audit.py`.** Counts, verdicts, plan actions and tallies are its output; copy them, never estimate them.

## Steps

### 1. Pre-flight

```
<py> <audit> host
```

`HOST=github|gitlab|CLI=gh|glab|REPO=<owner/repo>` names where the ledger lives. The CLI it names must be installed and authenticated; if it is not, run with `--dry-run` only and say so.

### 2. Freshness gate

```
<py> <audit> sources
```

For each `SOURCE=` line, fetch the page's verbatim bytes with the shell's HTTP client, following redirects:

```
curl -sSL --max-time 60 -o <scratch>/<id>.part -w "%{http_code} %{url_effective}" "<url>"
```

Only when curl exits 0 and the status is `200`, rename `<id>.part` to `<id>.md`. A failed download stays a `.part` file, so `diff-source` reports `not-checked` instead of hashing partial bytes. A tool that summarises or converts pages cannot establish a hash; if verbatim fetching is unavailable (a proxy, no network), skip the fetch — every source is then `not-checked` and the scan still runs. Independent fetches may run in parallel. Then, per source:

```
<py> <audit> diff-source --id <id> --file <scratch>/<id>.md --final-url <url_effective>
```

Keep every `VERDICT=unchanged|changed|new-guide|not-checked|…` line.

**Any `changed` or `new-guide` → skip steps 3–4** and continue at step 5 with `"scan_ran": false`. Scanning against a rule-set now known to be stale would produce findings the next rule-set contradicts. The digest tells the reader to re-vendor `rules.md` and `sources.toml` from `fleet-config` once that repo has updated them; this skill never edits them.

### 3. Plan and lint

```
<py> <audit> plan [--repo <name>]... [--rescan-all]
```

Keep every line. `REPOS=` names the (at most two) repos; `PLAN=<path>|action=scan|skip|unmeasured|…|sha=…|audience=…|kind=…` per file; for each planned scan, `SECTION=` lines for vendor-scoped sections, `HIT=<path>:<line>|rule=…|cap=violation|consider|…|text=…` lint candidates and one `HITS=` summary; `DEFERRED=<repo>|scan=N` for repos left to later runs; a closing `LEDGER=` line. `LEDGER=unreadable` means the ledger could not be read (every file plans as a scan — the safe direction); report it.

Nothing with `action=scan` → skip step 4; the digest still posts and lists the skipped files.

### 4. Judgment pass (serial, this session)

Read `rules.md` once, in full. Then, one planned-scan file at a time, read the file in full and assess every rule whose `file:` scope covers the file's `kind` and whose tag applies to its `audience` (a single-vendor rule does not apply inside a section scoped to the other vendor; a `[conflict]` rule applies only to neutral readers). Every `HIT=` candidate gets a verdict: `violation` or `consider` (never stronger than its `cap`) when the rule's `Why:` genuinely applies, otherwise it is a false positive and is left out. Judgment-only rules get `violation` or `consider` from the reading; a rule that could not be established is `unmeasured`, never compliant. `text` is the offending line copied verbatim.

Record for each file a list of findings shaped `{"rule": "R-NN", "verdict": "violation|consider|unmeasured", "line": <n or null>, "text": "<verbatim line or empty>", "note": "<one clause>"}`; a file with nothing to report gets `[]`. Keep the five most material findings per file — `audit.py` drops anything past five regardless and counts it.

### 5. Render the digest

Write `<scratch>/run.json`:

```json
{
  "date": "<YYYY-MM-DD>",
  "dry_run": false,
  "sources": ["<every VERDICT= line>"],
  "update_issue": null,
  "scan_ran": true,
  "plan": ["<every PLAN= line>"],
  "deferred": ["<every DEFERRED= line>"],
  "judgments": {"<path>": [<findings>]}
}
```

A planned file left out of `judgments` (or set to `null`) is unmeasured. Then:

```
<py> <audit> digest --run <scratch>/run.json > <scratch>/digest.md
```

`DIGEST=status=complete|partial` goes to stderr. The digest's second line is an ASCII stamp, `<!-- prompt-audit-digest run=<date> status=<status> scan=posted|dry-run|not-run update-issue=none -->`, the same stamp the private tool writes.

`--dry-run` → print `digest.md`, run `<py> <audit> ledger-write --run <scratch>/run.json --dry-run`, and stop.

### 6. Record and post

1. `<py> <audit> ledger-write --run <scratch>/run.json` — records each file judged with no `unmeasured` rule at its `PLAN=` sha; creates the `prompt-audit ledger` issue (label `audit-meta`) on the first run. It refuses to write when the ledger cannot be read, rather than risk a duplicate.
2. `<py> <audit> comment --body-file <scratch>/digest.md` — posts the digest; capture `LEDGER_COMMENT=`.

A failed write is reported with its error; the run does not claim delivery without the comment.

### 7. Report

A few lines: `status`, guides (sources checked / not-checked / changed), repos audited and repos deferred, files scanned / skipped / unmeasured, violation / consider totals, findings held back by the cap, and the ledger comment URL (or "dry run").

## Notes

- **Deliberate near-duplicate.** `audit.py` repeats helpers from `fleet-config`'s `.claude/skills/prompt-audit/audit.py` (hashing, frontmatter read, rule parsing, lint, ledger parse and render, digest). Self-containment is the fleet-config-lite contract — no shared `_lib`, no dependency on another checkout — so a duplication audit should not flag it. `rules.md` and `sources.toml` are byte-identical copies; the source commit is recorded in this repo's README.
- **One ledger format.** The ledger uses the same `<!-- audit-managed: kind=prompt-audit -->` marker, title and hidden `<!-- prompt-audit-ledger -->` block as the private tool, so either tool reads the other's ledger unchanged. The rubric hash is line-ending normalised, so both tools agree on it.
- **`global-instructions.md` is the neutral counterpart of `fleet-config`'s `global-CLAUDE.md`.** It is scanned first, and it is where shared text belongs: a line that also sits in `project-scaffolding/CLAUDE.md` is collapsed to one digest entry with the repos that carry it, so it is fixed once at the source rather than N times.
- **Why no cleanup issues.** The private tool files per-repo `prompt-drift` issues for its cleanup bucket; this repo's `/cleanup-fleet` has no such bucket, so those issues would have no consumer. Findings stay in the digest; a human files work from it with `/issue-add`.
- **Why a guide change stops the scan and files nothing here.** The rule-set is canonical in `fleet-config`; editing it here would break the byte-identical copy. The digest names the moved source instead.
- **Host.** The GitHub path is exercised live against this repo. The GitLab path follows `glab`'s documented CLI shape and is unit-tested with a stubbed runner, but is not live-tested where `glab` is not installed.
