# fleet-config-lite

Minimal companion repo for [app-launcher-lite](https://github.com/ferraroroberto/app-launcher-lite): the GitHub-Copilot-CLI-side machinery that makes the lite Board's session columns and the issue workflow work. No LLM calls, no schedulers — just hooks, skills, an installer, and the helper side of the lite fleet chief. (`skills/learning-log/` and `skills/prompt-audit/` are deliberate, narrow exceptions to "no LLM calls" — see their own sections below — and, like every skill here, are manual-invoke only.)

Downscaled from the private `fleet-config`; when a capability is missing here, port it from there deliberately rather than re-inventing it.

## What's here

| Path | Role |
|---|---|
| `hooks/session_state.py` | **Sole writer** of `sessions-state.json` — one row per live Copilot session (`working` / `needs-you` / `idle`), consumed read-only by app-launcher-lite's Board; the status machine is declared in [`docs/session-state.md`](docs/session-state.md) |
| `hooks/chief_inbox.py` | The chief's mailbox writer, called from `session_state.py`: a chief-dispatched worker's `agentStop` / `sessionEnd` becomes one event file in `~/.copilot/hooks/state/chief-inbox/` (fleet-config's mailbox v2 format); every other session is a no-op — see [docs/chief.md](docs/chief.md) |
| `hooks/chief_guard.py`, `hooks/chief-guard.template.json` | The chief's guard hooks: the handover log at `sessionStart`, turn-end holds at `agentStop` (compaction due, idle worker slots), an `ask_user` deny at `preToolUse` for the chief and chief-managed lanes, and at `userPromptSubmitted` lite's own copy of a skill swapped in for a foreign one in lite's sessions. `install.ps1` renders the template into `~/.copilot/hooks/` — see [docs/chief.md](docs/chief.md) |
| `hooks/_lib.py` | Payload helpers: camelCase→snake_case normalization, stdin JSON, cwd resolution |
| `hooks/session-state.template.json` | Copilot CLI hook definition (rendered with absolute paths by the installer) |
| `skills/issue-{add,start,finish,yolo}/` | Lite GitLab (`glab`) issue-workflow skills, discovered by Copilot from `~/.copilot/skills/` |
| `skills/e2e/` | Proportionate e2e skill (needs the sibling `skills/_lib/`): `SKILL.md` + `e2e_route.py` + the bundled `classify_e2e.py` router — see "The /e2e skill" below |
| `skills/quick/` | Trunk-commit lane below the issue threshold: one capped, verified commit straight to the default branch (no issue, no MR), auto-escalating to the issue workflow when the change outgrows its caps — the sanctioned exception to "never commit directly to the default branch" declared in `global-instructions.md` |
| `skills/learning-log/` | Host-agnostic (GitHub or GitLab) learning log + productivity stats from this repo's sibling-repo work stream: `SKILL.md` + stdlib `gather.py` (needs the sibling `skills/_lib/`) — see "The /learning-log skill" below |
| `skills/codebase-audit/`, `skills/audit-fleet/`, `skills/cleanup-fleet/` | Gated, credit-bounded resting-state quality audit: `SKILL.md` + `audit_gate.py` (significance gate, ledger, managed-issue upsert; `gh` or `glab`; needs the sibling `skills/_lib/`), a sequential fleet loop, and a one-repo-per-run fix loop — see "The audit skills" below |
| `skills/prompt-audit/` | Capped audit of instruction files (at most 2 repos per run, this repo and its siblings) against the vendors' current prompting guides: `SKILL.md` + byte-identical `rules.md`/`sources.toml` + `audit.py` and its sibling `audit_lint.py` (freshness gate, lint, skip-unchanged ledger, digest; `gh` or `glab`; needs the sibling `skills/_lib/`) — see "The /prompt-audit skill" below |
| `skills/slides/` | Two-phase HTML presentation builder (briefing gate → component-composed, Chrome-verified 16:9 slides): `SKILL.md` + `assets/` (design system, component catalog, criteria, template, icon gallery, examples) + stdlib-only `scripts/` (`propagate.py` style fan-out, `make_print.py` print/PDF export), ported from the private life-os repo (`assets/` byte-for-byte; the scripts differ only in writing through `skills/_lib/runtime_files.py` and hiding the console window through `skills/_lib/no_window.py`) |
| `skills/_lib/chief_ops.py`, `chief_plan.py`, `chief/` | The lite fleet chief's helper side: `chief_ops.py` (`board`, `sessions`, guard-railed `dispatch`, `open` (a plain session with a first message), `say --verify`, `stop`, `exchange`, `issues` and `verify` through `glab`, plus `plan` / `note` / `inbox` / `ack`) and `chief_managed.py mark` drive app-launcher-lite (its webapp port) and read and write `chief-plan.json`, `chief-journal.jsonl`, the `chief-inbox/` mailbox and `chief-managed.json` under `~/.copilot/hooks/state/` in the full fleet-config format app-launcher-lite reads; byte-identical ports with their provenance in [docs/chief.md](docs/chief.md) |
| `.github/skills/chief/` | The lite chief skill (about 8 KB, model-agnostic): the launcher spawns the chief in this checkout and types `/chief`. Copilot loads it as a project skill, so it exists only in this repo's sessions and is never junctioned into `~/.copilot/skills/` |
| `global-instructions.md` | Canonical, agent-agnostic global instructions; `install.ps1` links it to `~/.copilot/copilot-instructions.md` (see "The global instructions file" below) |
| `scripts/copilot_probe.py` | Re-runnable Copilot CLI capability probe: records each behaviour the chief port relies on as `verified`, `unsupported` or `unknown` per installed CLI version — see "Probing the installed Copilot CLI" below |
| `scripts/*_ratchet.py`, `.*-ratchet-baseline.json` | Ten vendored baseline-and-ratchet quality gates (static, structure, instruction, doc-refs, dead-code, conventions, docs, comment, runtime write, request budget), test-time only — see "The ratchets" below |
| `install.ps1` | Wires everything into `%USERPROFILE%\.copilot\` (idempotent) |

## Install

```powershell
git clone https://github.com/ferraroroberto/fleet-config-lite
cd fleet-config-lite
powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1
```

Then restart any running Copilot CLI session (hook configs load at startup).

### Fresh machine

1. Install Python 3.11+ (a real install, not the WindowsApps alias) and GitHub Copilot CLI (`winget install GitHub.Copilot`), then run `copilot login`.
2. Install `glab` (`winget install GLab.GLab`) and run `glab auth login` against your GitLab host.
3. Clone this repo and app-launcher-lite side by side (the launcher finds this checkout as its sibling `fleet-config-lite`).
4. Run `install.ps1`. It renders the two hook configs, links the instructions and skills, creates this checkout's `.venv` (the launcher runs the chief helpers through `.venv\Scripts\python.exe`), and ends with a checklist. Each line is `[ok]`, `[missing]` with the command that fixes it, or `[unknown]`: Copilot CLI and its version, `glab` and its sign-in for the configured GitLab host (the https GitLab remote of this checkout or a sibling; `[unknown]` when there is none, never `[missing]` on a guess), whether git itself reaches GitLab with no prompt (next step), the venv, and whether app-launcher-lite's session-host answers on the port its `config.json` sets.
5. Let git reach GitLab with no prompt. `glab auth login` stores its token for `glab` alone; `git` asks its own credential helper (Git Credential Manager on Windows), which holds no GitLab credential, so a lane's first `git fetch` fails with `could not read Username ... terminal prompts disabled` while `glab auth status` reads signed in. Read the `git reaches GitLab` line of the checklist (it needs one https GitLab remote to ask, in this checkout or a sibling checkout). When it reads `[missing]`, it prints the fix for your host; run it yourself, since the installer never edits your git config. It wires `glab` as the host-scoped credential helper, in two lines (the empty first value switches Git Credential Manager off for that host only; type each line separately in PowerShell):

   ```powershell
   git --% config --global --add credential.https://gitlab.com.helper ""
   git config --global --add credential.https://gitlab.com.helper "!glab auth git-credential"
   ```

   Re-run `install.ps1`: the line should read `[ok]`. `[unknown]` means the check could not ask (no https GitLab remote yet, or git failed for a non-credential reason such as the network); it is never read as `[ok]`. For a self-managed host, put its hostname where `gitlab.com` stands. A host that already routes to `glab` yet is still refused needs `glab auth login --hostname <host>` instead; the installer prints that when it sees the helper wired. `glab auth login --setup-git-credential-helper` is glab's own flag for the same wiring, but it is part of a sign-in, so it is not what the installer prints. `skills/_lib/gitlab_git_access.py check` prints the same verdict as `GIT_ACCESS=` / `FIX=` lines for any other checker to reuse.
6. Restart any running Copilot session (hook configs load at startup), then run `python scripts\copilot_probe.py run --live` and record the manual items you check.
7. Settings > Chief > Doorbell in app-launcher-lite is the owner's choice: on, it rings an idle Copilot chief when the session host knows the composer is empty; off, only the owner's own messages wake it ([docs/chief.md](docs/chief.md)). The chief reads its mailbox at the start of every turn.

`install.ps1 -SkipVenv -SkipChecklist` skips the last two steps (the tests use it).

### A machine that also runs the full fleet

If `~/.copilot/skills` or `~/.agents/skills` is a link into another tree, the full fleet runs on this PC too. The installer prints `[note] shared machine` and writes nothing that would change any other session:

| User-scope path | Shared machine | Dedicated machine |
|---|---|---|
| `~/.copilot/hooks/fleet-config-lite-session-state.json` | written with `--lite-sessions-only`: the hook records a session only when app-launcher-lite's own session-host lists its launcher id, and returns before any write otherwise | written; records every Copilot session |
| `~/.copilot/hooks/fleet-config-lite-chief-guard.json` | written; it acts only for lite's chief, the lanes in lite's registry, and (for the skill swap) the sessions app-launcher-lite's session-host lists, and returns at once for every other session | written |
| `~/.copilot/hooks/state/` | created if missing; lite's own state files live here | created if missing |
| `~/.copilot/copilot-instructions.md` | skipped (a global instructions file reaches every Copilot session) | linked, only when free or already ours |
| `~/.copilot/skills/<name>` | skipped (lite skills would appear beside the full fleet's) | junctioned, never over a skill that isn't ours |

Because the skills are not junctioned, a lane's `/issue-start` resolves to the full fleet's GitHub skill on a shared machine, and Copilot gives that user-scope skill precedence over any extra skills folder (`COPILOT_SKILLS_DIRS`, `copilot skill add`). So the chief guard's `userPromptSubmitted` hook swaps the expanded skill in the prompt itself: in any session app-launcher-lite's session-host lists, a skill this checkout also ships that was expanded from another folder is replaced with this checkout's `SKILL.md` before the first model turn, so every model starts on lite's skill. As backstops, `chief_ops.py dispatch` opens every brief with the paths of this checkout's own `issue-start` (or `issue-yolo`) and `issue-finish`, and the guard denies a chief-managed lane's shell call that runs `gh`, `notify_complete`, or a helper from the full fleet's skills folder. A lane therefore follows lite's skill, runs only `glab`, and sends no full-fleet notification. A dedicated machine is unchanged: its skills already come from this checkout, so the prompt is left alone and the guard stays silent ([docs/chief.md](docs/chief.md)).

A user-scope target that is itself a link into another tree (the Copilot home, its `hooks` folder, a hook config, the skills folder) is never written through: it is skipped with a `[skip] ... is a link into another tree` line. The repo-local `.venv` is created either way.

Requirements: Windows, Python 3.11+ on a real install path (the WindowsApps alias is rejected), GitHub Copilot CLI ≥ 1.0.70, `glab` authenticated against your GitLab host for the skills.

`install.ps1` also links `global-instructions.md` into `~/.copilot/copilot-instructions.md` (symlink, falling back to a plain copy if symlinks aren't available; the copy starts with a `<!-- fleet-config-lite: managed copy ... -->` marker line). It only replaces a file it can positively identify as its own: a symlink pointing at this checkout, a plain file starting with that marker, or a plain file byte-identical to `global-instructions.md`. Anything else — your own hand-written instructions file, or the private `fleet-config`'s larger `global-CLAUDE.md` linked there — is left untouched and the installer prints `[skip]`; move or delete it and re-run if you want the installer to manage the path.

### app-launcher-lite on other ports

app-launcher-lite sets its own two ports in its `config/config.json` (`webapp.port`, default 8465, and `webapp.session_host_port`, default 8466) so it can run beside a full launcher on one PC. The session-state hook, the chief helpers, the GitLab namespace read and the installer's session-host probe all read them through `skills/_lib/lite_ports.py` from the sibling `app-launcher-lite` checkout, so none of them reaches the other launcher. `FLEET_LITE_CONFIG` names a different `config.json`; a missing or unusable file means the default ports. `FLEET_LITE_SESSION_HOST` still overrides the session-host list URL for the hook alone, and `--base-url` the webapp URL for one chief call.

## The global instructions file

`global-instructions.md` is a small, agent-agnostic seed — the lite counterpart of `fleet-config`'s `global-CLAUDE.md`. It names no specific agent: `install.ps1` links it to Copilot CLI's `copilot-instructions.md` today, and the same file can be junctioned or copied by hand to `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, or `~/.pi/agent/AGENTS.md` if you use those agents too — fleet-config-lite doesn't auto-wire them since its own hooks/skills are Copilot-CLI-specific. Deliberately small; grow it as real corrections accumulate, don't port the private fleet-config's fleet-wide sections (multi-repo map, local LLM hub, design system, etc.) — those are out of scope here.

### Skills can come from any repo

Copilot discovers whatever sits in `~/.copilot/skills/` — the junction target is irrelevant. This repo's `skills/` is just one source; a separate team skills repo plugs in exactly the same way: junction its skill folders into `~/.copilot/skills/` (or use `copilot skill add <dir>`), and every Copilot session — including the ones App Launcher Lite's Board buttons spawn — can invoke them. `install.ps1` only ever touches junctions that point into *this* checkout, so it coexists safely with skills installed from anywhere else.

## The /e2e skill

`skills/e2e/` decides, runs, and maintains a project's end-to-end tests **proportionate to the actual diff**: a target repo declares path→tier rules in its own `.fleet.toml [e2e]` table, the bundled `classify_e2e.py` maps the changed files to `skip` / `static` / `full` (anything unmatched, malformed, or empty fails safe to `full` — uncertainty always escalates, never narrows), and the skill runs only that slice. `issue-finish` and `issue-yolo` call it before every merge request; it also runs standalone (`/e2e`, `/e2e plan`, `/e2e full`). On a repo without the router, it self-heals by copying the bundled classifier in byte-verbatim.

The folder depends on no other repo or checkout, only on its sibling `skills/_lib/` (`e2e_route.py` writes through `runtime_files.py`): junction both (the installer junctions every folder under `skills/`) and it works anywhere with Python 3.11+. A copy of `skills/e2e/` alone fails at import. Provenance: `classify_e2e.py` is vendored byte-verbatim from `project-scaffolding` `scripts/classify_e2e.py`; the kept-current record is the `classify_e2e` row in `.fleet.toml`'s `[vendored]` table. Re-vendor deliberately by replacing the file whole, never by editing it.

## The /learning-log skill

`skills/learning-log/` is a host-agnostic port of the private `fleet-config`'s `.claude/skills/learning-log`: on manual invocation it reads merged PRs/MRs + closed issues since the last run — across this repo and its public siblings under the same owner/group — computes exact bucketed productivity stats, fans out one insight sub-agent per work-type bucket, and upserts a ledger issue + weekly-shaped comment. `gather.py` detects whether this repo's `origin` remote is GitHub or GitLab (`git remote get-url origin`) and drives `gh` or `glab` accordingly; the GitHub path is exercised live against this repo, the GitLab path follows `glab`'s documented CLI shape but isn't live-tested here (`glab` isn't installed on this dev machine, the same caveat already accepted for this repo's other `glab`-based skills).

It is a deliberate, narrow exception to this repo's "no LLM calls" principle — the insight-extraction step is model-agnostic (never hardcodes a vendor/model name) and low-effort by design — but keeps "no schedulers": there is no unattended entry point, only `/learning-log`.

## The audit skills

Three skills port the private `fleet-config`'s `/codebase-audit` → `/audit-fleet` → `/cleanup-fleet` discipline, downscaled for a limited-credit setup: **`/codebase-audit`** reads one repo as a senior developer would and files findings into at most four living-backlog issues (`audit: bug|stale|slop|documentation findings`, one per bucket, reused across runs, max 5 new findings per bucket per run); **`/audit-fleet`** walks the sibling repos and audits at most 2 per run, sequentially; **`/cleanup-fleet <bucket>`** works one repo's bucket issue per run through this repo's own `/issue-yolo` (easy) or a build-and-stop `/issue-start` (hard). No sub-agents, no scheduler, no notifications; a security finding is reported to the terminal only and never written to an issue.

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

## How the session hooks work

Copilot CLI fires native hooks (user scope: `~/.copilot/hooks/*.json`). The payloads are **camelCase** and carry **no event name** (verified live against CLI 1.0.70), so the rendered config passes the event as `argv[1]`:

- `userPromptSubmitted` → row status `working`
- `agentStop` → row status `needs-you` (also records `transcriptPath`)
- `sessionEnd` → row deleted (hard kills age out via a 24 h prune)
- `sessionStart` → creates an `idle` row but **never downgrades** an existing one (in `-p` mode it fires *after* `userPromptSubmitted`)

These rules live in one function, `next_transition`; [`docs/session-state.md`](docs/session-state.md) has the state table and how to add a status or event.

State file: `%USERPROFILE%\.copilot\hooks\state\sessions-state.json`. App Launcher Lite reads it there by default. Sessions launched from App Launcher Lite inherit `APP_LAUNCHER_SESSION_ID` / `APP_LAUNCHER_AGENT`, which the writer persists for an exact join; external sessions fall back to a cwd match.

All hooks are advisory-only: every failure is swallowed and the hook exits 0 — a broken hook can never disturb the Copilot session it observes.

## Tests

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt   # ruff, for the static ratchet below
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The hooks and skills are stdlib only; the test run's one dev dependency is ruff (`requirements-dev.txt`, pinned), and nothing in it ships to the machines `install.ps1` wires up.

### The ratchets

Ten vendored baseline-and-ratchet quality gates run inside `python -m unittest discover -s tests` — each wraps a `project-scaffolding` script byte-for-byte, declared in `.fleet.toml`'s `[vendored]` table and configured by its own table there. All ten share the same mechanics: existing debt sits in a committed `.<name>-ratchet-baseline.json`, baselined and never excluded, so nothing may grow past its baselined count; shrink a baseline with `--update-baseline`, grow one only with the explicit `--allow-additions` flag (which shows in review); and exit 3 — the detector could not run — always fails the test as **NOT CONFIRMED**, never folded into a pass. Every baseline here is empty today except the request budget's three, and none needs anything beyond stdlib to run except the static ratchet.

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
| runtime write | a Python write target resolving under a code folder (`hooks/`, `skills/`, `scripts/`) beyond the baseline; a new target it cannot resolve is NOT CONFIRMED | `[runtime_write_ratchet]` |
| request budget | a rising count of fixed-rate browser polls, poll intervals under 2 s, undeclared fast server loops, directory scans in request handlers, default-pool submits, or a web app without the timing middleware | `[request_budget_ratchet]` |

Per-ratchet specifics that don't fit the table — the static ratchet's extra prerequisites (ruff + Node's `npx` for `jscpd`), the guarded writer behind the runtime-write ratchet, and the rest — live in [docs/ratchets.md](docs/ratchets.md).

## Copilot hook gotchas

**Interactive firing is version-dependent.** CLI 1.0.70 fired the four hooks only in `-p` runs, not in an interactive TUI session ([interactive sessionStart/End mis-timed](https://github.com/github/copilot-cli/issues/991), [sessionStart doesn't run at CLI startup](https://github.com/github/copilot-cli/issues/2201)); CLI 1.0.105 was observed firing all four in both. The probe below records `-p` firing live and keeps interactive firing as a manual item, `unknown` until someone records it on the installed version. When interactive hooks do not fire, the Board degrades as designed: live sessions still appear (session-host presence), with status "unknown" and a "session state unavailable" note.

The remaining failure modes are **silent** — the session runs fine, the hook just never fires:

- **No BOM.** A hook config saved as UTF-8-with-BOM is ignored. Windows PowerShell 5.1's `Set-Content -Encoding utf8` writes a BOM; the installer uses `[IO.File]::WriteAllText` (BOM-less) for exactly this reason.
- **One dot in the filename.** `foo.session-state.json` is ignored; `foo-session-state.json` loads.
- Hook configs load at CLI startup only — restart the session after installing.
- Payloads carry no event-name field; the config passes the event as `argv[1]`.
- **No stdin pipe in the hook command.** Copilot runs the `powershell` key under pwsh 7 (CLI 1.0.83). `[Console]::In.ReadToEnd() | python ...` decodes the payload with the console's OEM code page first, garbling any non-ASCII prompt or cwd (`???` in 5.1, cp850 mojibake in pwsh). The template invokes Python directly (`& python session_state.py <event>`), which inherits the raw UTF-8 bytes in both shells; `tests/test_session_state.py` drives the template's own command to keep it that way.

## Probing the installed Copilot CLI

`scripts/copilot_probe.py` keeps one report, `~/.copilot/hooks/state/copilot-probe.json`, of the Copilot behaviours the chief port depends on. Every item is `verified`, `unsupported` or `unknown`; a result recorded on another CLI version drops back to `unknown` (its old status stays as evidence), so re-run it after every `copilot update` and on every new machine.

```powershell
.venv\Scripts\python.exe scripts\copilot_probe.py run           # static checks only: version and flags, spends nothing
.venv\Scripts\python.exe scripts\copilot_probe.py run --live    # plus one copilot -p request in a throwaway trusted folder
.venv\Scripts\python.exe scripts\copilot_probe.py record composer_keys_doorbell verified --evidence "what you saw"
.venv\Scripts\python.exe scripts\copilot_probe.py report        # print the stored report
```

The live leg installs repo-level hooks (`.github/hooks/probe.json`) in a temp git folder, trusted for that run through `COPILOT_ALLOW_ALL=true`. They log every event, inject a nonce through `sessionStart` and block the first `agentStop`. That run settles four items: `-p` hook firing, `sessionStart` `additionalContext` reaching the model, `agentStop` `decision: block` forcing another turn, and `session.usage_record` carrying `inputTokens` / `maxPromptTokens` in the session's `events.jsonl`. A second request installs a `preToolUse` hook that denies every tool call and asks for a shell command that would create a file: the file staying absent settles whether `permissionDecision: deny` stops the call. The interactive-only items (composer keys for the doorbell, a mid-turn `/compact <focus>` running at turn end, `/remote on` from the launcher, a background shell waking the agent, `ask_user` under autopilot, interactive hook firing, `--session-id` resume) need a live TUI and are recorded by hand with `record`.

## Verifying the hooks live

1. `install.ps1`, then open a fresh Copilot session in any repo.
2. Submit a prompt → the state file shows the row as `working`.
3. Let the turn finish → `needs-you`.
4. `/exit` → the row disappears.
