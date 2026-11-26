# fleet-config-lite

Companion repo for [app-launcher-lite](https://github.com/ferraroroberto/app-launcher-lite): the skills and the global instructions file that sit beside its GitHub-Copilot-CLI side. No hooks, no chief, no LLM calls of its own, no schedulers. (`skills/learning-log/` and `skills/prompt-audit/` are deliberate, narrow exceptions to "no LLM calls" — see their own sections below — and, like every skill here, are manual-invoke only.)

Downscaled from the private `fleet-config`; when a capability is missing here, port it from there deliberately rather than re-inventing it.

## Where the rest went

The Copilot hooks (session state, chief inbox, chief guard), the lite fleet chief with its helpers, and the lane skills (`issue-add`, `issue-start`, `issue-finish`, `issue-yolo`, `e2e`, `quick`) are owned by app-launcher-lite, in its `copilot/` folder, and are edited there. This repo no longer carries a copy, so the two cannot drift or be installed side by side. A machine still wired to this repo's old install moves over with app-launcher-lite's `copilot\install.ps1 -Migrate`; its `docs/migrating-from-fleet-config-lite.md` gives the order to do it in, and `copilot/docs/chief.md` and `copilot/docs/session-state.md` there document the chief and the session-state hook.

## What's here

| Path | Role |
|---|---|
| `skills/learning-log/` | Host-agnostic (GitHub or GitLab) learning log + productivity stats from this repo's sibling-repo work stream: `SKILL.md` + stdlib `gather.py` (needs the sibling `skills/_lib/`) — see "The /learning-log skill" below |
| `skills/codebase-audit/`, `skills/audit-fleet/`, `skills/cleanup-fleet/` | Gated, credit-bounded resting-state quality audit: `SKILL.md` + `audit_gate.py` (significance gate, ledger, managed-issue upsert; `gh` or `glab`; needs the sibling `skills/_lib/`), a sequential fleet loop, and a one-repo-per-run fix loop — see "The audit skills" below |
| `skills/prompt-audit/` | Capped audit of instruction files (at most 2 repos per run, this repo and its siblings) against the vendors' current prompting guides: `SKILL.md` + byte-identical `rules.md`/`sources.toml` + `audit.py` and its sibling `audit_lint.py` (freshness gate, lint, skip-unchanged ledger, digest; `gh` or `glab`; needs the sibling `skills/_lib/`) — see "The /prompt-audit skill" below |
| `skills/slides/` | Two-phase HTML presentation builder (briefing gate → component-composed, Chrome-verified 16:9 slides): `SKILL.md` + `assets/` (design system, component catalog, criteria, template, icon gallery, examples) + stdlib-only `scripts/` (`propagate.py` style fan-out, `make_print.py` print/PDF export, `build_catalog.py`, which generates `assets/catalog.json` from the `components.md` ledger and checks the two for drift, and `lint_deck.py`, which classifies a deck's CSS as catalog, deck-local or ad-hoc, gates "final" on exit 0, and writes an inventory report beside an older deck), ported from the private life-os repo and since extended here: the component catalog is a versioned ledger with use-when rules and anchored CSS blocks |
| `skills/_lib/` | The helpers those skills share: `issue_host.py` (remote-URL parser, managed-issue marker, gh/glab issue argv), `git_run.py` (the one `git` spawn), `no_window.py`, and `runtime_files.py` with its `fleet_core/` guarded writer |
| `global-instructions.md` | Canonical, agent-agnostic global instructions; `install.ps1` links it to `~/.copilot/copilot-instructions.md` (see "The global instructions file" below) |
| `scripts/*_ratchet.py`, `.*-ratchet-baseline.json`, `.ratchets/` | Twelve vendored baseline-and-ratchet quality gates (static, structure, instruction, doc-refs, dead-code, conventions, docs, comment, runtime write, request budget, port host, clean tree), test-time only — see "The ratchets" below |
| `install.ps1` | Links the instructions file and the skills above into `%USERPROFILE%\.copilot\` (idempotent) |

## Install

```powershell
git clone https://github.com/ferraroroberto/fleet-config-lite
cd fleet-config-lite
powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1
```

Install app-launcher-lite's `copilot/` folder separately (`copilot\install.ps1`) for the hooks, the chief and the issue skills. The two installers write different things; run this one last on a machine that migrates, because app-launcher-lite's `-Migrate` removes every skill link into a fleet-config-lite checkout and this installer puts back the ones this repo still owns.

`install.ps1` links `global-instructions.md`, junctions each folder under `skills/` into `~/.copilot/skills/`, creates this checkout's `.venv` (stdlib only; the audit and learning-log helpers run through it) and ends with a checklist: Copilot CLI, `glab` and the venv, each `[ok]` or `[missing]` with the command that fixes it. It also prints a `[warn]` for a hook config or a skill link an older install of this repo left behind, and never deletes one: app-launcher-lite's `-Migrate` owns that move. `-SkipVenv -SkipChecklist` skips the last two steps (the tests use it).

Requirements: Windows, Python 3.11+ on a real install path (the WindowsApps alias is rejected), GitHub Copilot CLI, `glab` authenticated against your GitLab host for the skills.

### A machine that also runs the full fleet

If `~/.copilot/skills` or `~/.agents/skills` is a link into another tree, the full fleet runs on this PC too. The installer prints `[note] shared machine` and writes nothing that would change any other session:

| User-scope path | Shared machine | Dedicated machine |
|---|---|---|
| `~/.copilot/copilot-instructions.md` | skipped (a global instructions file reaches every Copilot session) | linked, only when free or already ours |
| `~/.copilot/skills/<name>` | skipped (these skills would appear beside the full fleet's) | junctioned, never over a skill that isn't ours |

A user-scope target that is itself a link into another tree (the Copilot home, the skills folder) is never written through: it is skipped with a `[skip] ... is a link into another tree` line. The repo-local `.venv` is created either way.

`install.ps1` links `global-instructions.md` into `~/.copilot/copilot-instructions.md` (symlink, falling back to a plain copy if symlinks aren't available; the copy starts with a `<!-- fleet-config-lite: managed copy ... -->` marker line). It only replaces a file it can positively identify as its own: a symlink pointing at this checkout, a plain file starting with that marker, or a plain file byte-identical to `global-instructions.md`. Anything else — your own hand-written instructions file, or the private `fleet-config`'s larger `global-CLAUDE.md` linked there — is left untouched and the installer prints `[skip]`; move or delete it and re-run if you want the installer to manage the path.

## The global instructions file

`global-instructions.md` is a small, agent-agnostic seed — the lite counterpart of `fleet-config`'s `global-CLAUDE.md`. It names no specific agent: `install.ps1` links it to Copilot CLI's `copilot-instructions.md` today, and the same file can be junctioned or copied by hand to `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, or `~/.pi/agent/AGENTS.md` if you use those agents too — fleet-config-lite doesn't auto-wire them since its installer is Copilot-CLI-specific. Deliberately small; grow it as real corrections accumulate, don't port the private fleet-config's fleet-wide sections (multi-repo map, local LLM hub, design system, etc.) — those are out of scope here.

### Skills can come from any repo

Copilot discovers whatever sits in `~/.copilot/skills/` — the junction target is irrelevant. This repo's `skills/` is just one source; a separate team skills repo plugs in exactly the same way: junction its skill folders into `~/.copilot/skills/` (or use `copilot skill add <dir>`), and every Copilot session — including the ones App Launcher Lite's Board buttons spawn — can invoke them. `install.ps1` only ever touches junctions that point into *this* checkout, so it coexists safely with skills installed from anywhere else.


## The /learning-log skill

`skills/learning-log/` is a host-agnostic port of the private `fleet-config`'s `.claude/skills/learning-log`: on manual invocation it reads merged PRs/MRs + closed issues since the last run — across this repo and its public siblings under the same owner/group — computes exact bucketed productivity stats, fans out one insight sub-agent per work-type bucket, and upserts a ledger issue + weekly-shaped comment. `gather.py` detects whether this repo's `origin` remote is GitHub or GitLab (`git remote get-url origin`) and drives `gh` or `glab` accordingly; the GitHub path is exercised live against this repo, the GitLab path follows `glab`'s documented CLI shape but isn't live-tested here (`glab` isn't installed on this dev machine, the same caveat already accepted for this repo's other `glab`-based skills).

It is a deliberate, narrow exception to this repo's "no LLM calls" principle — the insight-extraction step is model-agnostic (never hardcodes a vendor/model name) and low-effort by design — but keeps "no schedulers": there is no unattended entry point, only `/learning-log`.

## The audit skills

Three skills port the private `fleet-config`'s `/codebase-audit` → `/audit-fleet` → `/cleanup-fleet` discipline, downscaled for a limited-credit setup: **`/codebase-audit`** reads one repo as a senior developer would and files findings into at most four living-backlog issues (`audit: bug|stale|slop|documentation findings`, one per bucket, reused across runs, max 5 new findings per bucket per run); **`/audit-fleet`** walks the sibling repos and audits at most 2 per run, sequentially; **`/cleanup-fleet <bucket>`** works one repo's bucket issue per run through `/issue-yolo` (easy) or a build-and-stop `/issue-start` (hard), the issue skills app-launcher-lite installs from its `copilot/` folder. No sub-agents, no scheduler, no notifications; a security finding is reported to the terminal only and never written to an issue.

**The significance gate is what keeps it cheap.** `skills/codebase-audit/audit_gate.py gate` decides, deterministically, whether a repo deserves a read: it stores the last audited default-branch sha and rubric hash in a `codebase-audit ledger` issue (label `audit-meta`, the same block the private tool writes, so a repo audited by both keeps one ledger — this repo's is its open `audit-meta` issue), then counts added+deleted lines on the mainline since that sha over **source paths only** (docs, markdown, tests and lockfiles weigh nothing) and skips commits whose message references one of the repo's own audit issues (`Closes #N`, a `<type>/N-slug` branch). Below the threshold (default 1000, `--threshold N`) the repo accumulates and the run stops before reading a file; only real growth buys a re-read, so fixing audit findings never triggers the next audit. Every unknown — no ledger, an unreachable baseline, a diff it cannot read — fails open to `AUDIT`.

```powershell
.venv\Scripts\python.exe skills\codebase-audit\audit_gate.py gate             # {"decision": "SKIP_BELOW_THRESHOLD", ...}
.venv\Scripts\python.exe skills\codebase-audit\audit_gate.py get --kind slop   # the managed issue, or number: null
```

Host is detected from `origin` like `learning-log`: the GitHub path is exercised live against this repo, the GitLab path follows `glab`'s documented CLI shape but isn't live-tested here.

## The /prompt-audit skill

`skills/prompt-audit/` is a downscaled port of the private `fleet-config`'s `.claude/skills/prompt-audit` (lite scope). On manual invocation it checks whether the vendors' prompting guides moved past the vendored baselines (the session fetches each page verbatim; `audit.py diff-source` hashes it — an unfetched page is `not-checked`, never `unchanged`), lints the instruction files of this repo and its sibling repos (`global-instructions.md`, `CLAUDE.md`, `AGENTS.md`, `.github/copilot-instructions.md`, `.claude/rules/*.md`, `SKILL.md`), judges the lint candidates and judgment-only rules against `rules.md`, and posts one digest comment on a `prompt-audit ledger` issue (label `audit-meta`) in this repo. The ledger's marker, title and hidden block are the private tool's exact format, so either tool reads the other's ledger unchanged; a file whose sha is unchanged under the same rule-set hash is skipped on the next run.

Caps are hard-coded in `audit.py` and unit-tested: **at most 2 repos per run** (the rest are listed as deferred and rotate in on later runs), **at most 5 findings per file per run**, no sub-agents (the judgment pass runs serially in the invoking session), no scheduler, no notifications. Unlike the private tool it files no per-repo `prompt-drift` issues — this repo's `/cleanup-fleet` has no such bucket to consume them — and a moved guide stops the scan without filing anything here, because the rule-set is canonical upstream.

It is a deliberate, narrow exception to this repo's "no LLM calls" principle, the same carve-out as `learning-log`: the judgment step is model-agnostic (it never hardcodes a vendor or model name and runs in whichever session invoked it) while every count, hash and verdict cap comes from `audit.py`, and there is still no unattended entry point, only `/prompt-audit`.

**Port provenance.** `rules.md` and `sources.toml` are byte-identical copies, re-vendored by replacing the files whole, never by editing them here:

| File | Source | Commit | sha256 |
|---|---|---|---|
| `skills/prompt-audit/rules.md` | `fleet-config` `.claude/skills/prompt-audit/rules.md` | `ec8436d` | `19c3703c83113fd7d73d5a4756347e097e1cf7486aa8ba5ef20674b7ef852584` |
| `skills/prompt-audit/sources.toml` | `fleet-config` `.claude/skills/prompt-audit/sources.toml` | `ec8436d` | `257c77544604c3cce63f5b8c1b80fb76dc014f27414039dc605bb627eadf285b` |

The hashes are of the committed (LF) bytes; a checkout with `core.autocrlf=true` shows CRLF on disk, which `audit.py` normalises before hashing the rubric. `audit.py` itself is a near-duplicate of the private helper, not a copy; it shares its remote-URL, marker and gh/glab issue helpers with the other audit skills through `skills/_lib/issue_host.py`, and spawns `git` through `skills/_lib/git_run.py`.

```powershell
.venv\Scripts\python.exe skills\prompt-audit\audit.py host                  # HOST=github|CLI=gh|REPO=...
.venv\Scripts\python.exe skills\prompt-audit\audit.py plan                  # REPOS= (at most 2), PLAN=/HIT= lines, DEFERRED= repos
.venv\Scripts\python.exe skills\prompt-audit\audit.py ledger-write --run run.json --dry-run   # ARGV= lines, nothing spawned
```

Host is detected from `origin` like the other skills: the GitHub path is exercised live against this repo; the GitLab path is unit-tested with a stubbed runner (a GitLab origin drives `glab issue list/create/update/note`) but isn't live-tested here, since `glab` isn't installed on this dev machine.


## Tests

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt   # ruff, for the static ratchet below
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The skills are stdlib only; the test run's one dev dependency is ruff (`requirements-dev.txt`, pinned), and nothing in it ships to the machines `install.ps1` wires up.

### The ratchets

Twelve vendored baseline-and-ratchet quality gates run inside `python -m unittest discover -s tests` — each wraps a `project-scaffolding` script byte-for-byte, declared in `.fleet.toml`'s `[vendored]` table and configured by its own table there. All twelve share the same mechanics: existing debt sits in a committed baseline (`.<name>-ratchet-baseline.json`, or `.ratchets/<name>.json` for the newer ones), baselined and never excluded, so nothing may grow past its baselined count; shrink a baseline with `--update-baseline`, grow one only with the explicit `--allow-additions` flag (which shows in review); and exit 3 — the detector could not run — always fails the test as **NOT CONFIRMED**, never folded into a pass. Every baseline here is empty, the request budget's, port host's and clean tree's included. None needs anything beyond stdlib to run except the static ratchet.

| Ratchet | Fails on | Config table |
|---|---|---|
| static | a new duplicate block (`jscpd`), unused import/variable (ruff F401/F841), or curated ruff bug/security finding (B/S codes, `S113` included) | `[static_ratchet]` |
| structure | a file over 1,000 lines, a function over 100 lines, a directory over 40 modules, or a root layout that no longer matches `shape` + `extra_roots` | `[structure_ratchet]` |
| instruction | a `SKILL.md` (or a doc it links) gaining a prompt-audit rule hit, or passing a size cap | `[instruction_ratchet]` |
| doc-refs | a dangling repo path, `python -m` module, or relative link in `README.md`/`docs/**/*.md` | `[doc_refs_ratchet]` |
| dead-code | a Python function, class or method nothing else in the tree references | `[dead_code_ratchet]` |
| conventions | a rising count for an enabled fleet-convention `ast` rule (`no-window`, `logging-not-print`, `no-drive-path`, `subprocess-timeout`, `browser-per-iteration`) | `[conventions_ratchet]` |
| docs | `README.md` over 40 KiB, or a new history marker (issue reference, dated heading, changelog heading) | `[docs_ratchet]` |
| comment | a new issue reference inside a code comment | `[comment_ratchet]` |
| runtime write | a Python write target resolving under a code folder (`skills/`, `scripts/`) beyond the baseline; a new target it cannot resolve is NOT CONFIRMED | `[runtime_write_ratchet]` |
| request budget | a rising count of fixed-rate browser polls, poll intervals under 2 s, undeclared fast server loops, directory scans in request handlers, default-pool submits, or a web app without the timing middleware | `[request_budget_ratchet]` |
| port host | a port or machine-local host literal (private-LAN or tailnet address) written in tracked scripts or code (this repo reads no port, so the baseline is empty) | `[port_host_ratchet]` |
| clean tree | an install that adds, changes or deletes a tracked or untracked path: it runs `install.ps1` once against a scratch profile and compares `git status` before and after; NOT CONFIRMED when the smoke cannot run | `[clean_tree_ratchet]` |

Per-ratchet specifics that don't fit the table — the static ratchet's extra prerequisites (ruff + Node's `npx` for `jscpd`), the guarded writer behind the runtime-write ratchet, and the rest — live in [docs/ratchets.md](docs/ratchets.md).
