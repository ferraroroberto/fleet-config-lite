# fleet-config-lite

Minimal companion repo for [app-launcher-lite](https://github.com/ferraroroberto/app-launcher-lite): the GitHub-Copilot-CLI-side machinery that makes the lite Board's session columns and the issue workflow work. No LLM calls, no schedulers, no chief — just hooks, skills, and an installer. (`skills/learning-log/` and `skills/prompt-audit/` are deliberate, narrow exceptions to "no LLM calls" — see their own sections below — and, like every skill here, are manual-invoke only.)

Downscaled from the private `fleet-config`; when a capability is missing here, port it from there deliberately rather than re-inventing it.

## What's here

| Path | Role |
|---|---|
| `hooks/session_state.py` | **Sole writer** of `sessions-state.json` — one row per live Copilot session (`working` / `needs-you` / `idle`), consumed read-only by app-launcher-lite's Board |
| `hooks/_lib.py` | Payload helpers: camelCase→snake_case normalization, stdin JSON, cwd resolution |
| `hook-config/session-state.template.json` | Copilot CLI hook definition (rendered with absolute paths by the installer) |
| `skills/issue-{add,start,finish,yolo}/` | Lite GitLab (`glab`) issue-workflow skills, discovered by Copilot from `~/.copilot/skills/` |
| `skills/e2e/` | Self-contained proportionate e2e skill: `SKILL.md` + `e2e_route.py` + the bundled `classify_e2e.py` router — see "The /e2e skill" below |
| `skills/quick/` | Trunk-commit lane below the issue threshold: one capped, verified commit straight to the default branch (no issue, no MR), auto-escalating to the issue workflow when the change outgrows its caps — the sanctioned exception to "never commit directly to the default branch" declared in `global-instructions.md` |
| `skills/learning-log/` | Host-agnostic (GitHub or GitLab) learning log + productivity stats from this repo's sibling-repo work stream: `SKILL.md` + self-contained `gather.py` — see "The /learning-log skill" below |
| `skills/codebase-audit/`, `skills/audit-fleet/`, `skills/cleanup-fleet/` | Gated, credit-bounded resting-state quality audit: `SKILL.md` + self-contained `audit_gate.py` (significance gate, ledger, managed-issue upsert; `gh` or `glab`), a sequential fleet loop, and a one-repo-per-run fix loop — see "The audit skills" below |
| `skills/prompt-audit/` | Capped audit of instruction files (this repo plus at most 2 sibling repos per run) against the vendors' current prompting guides: `SKILL.md` + byte-identical `rules.md`/`sources.toml` + self-contained `audit.py` (freshness gate, lint, skip-unchanged ledger, digest; `gh` or `glab`) — see "The /prompt-audit skill" below |
| `skills/slides/` | Two-phase HTML presentation builder (briefing gate → component-composed, Chrome-verified 16:9 slides): `SKILL.md` + `assets/` (design system, component catalog, criteria, template, icon gallery, examples) + stdlib-only `scripts/` (`propagate.py` style fan-out, `make_print.py` print/PDF export), ported byte-for-byte in its `assets/`+`scripts/` from the private life-os repo |
| `global-instructions.md` | Canonical, agent-agnostic global instructions; `install.ps1` links it to `~/.copilot/copilot-instructions.md` (see "The global instructions file" below) |
| `install.ps1` | Wires everything into `%USERPROFILE%\.copilot\` (idempotent) |

## Install

```powershell
git clone https://github.com/ferraroroberto/fleet-config-lite
cd fleet-config-lite
powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1
```

Then restart any running Copilot CLI session (hook configs load at startup).

Requirements: Windows, Python 3.11+ on a real install path (the WindowsApps alias is rejected), GitHub Copilot CLI ≥ 1.0.70, `glab` authenticated against your GitLab host for the skills.

`install.ps1` also links `global-instructions.md` into `~/.copilot/copilot-instructions.md` (symlink, falling back to a plain copy if symlinks aren't available). If that path already belongs to something else — most commonly the private `fleet-config` linking its own, larger `global-CLAUDE.md` there — the installer detects it isn't ours and prints `[skip]` rather than overwriting it.

## The global instructions file

`global-instructions.md` is a small, agent-agnostic seed — the lite counterpart of `fleet-config`'s `global-CLAUDE.md`. It names no specific agent: `install.ps1` links it to Copilot CLI's `copilot-instructions.md` today, and the same file can be junctioned or copied by hand to `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, or `~/.pi/agent/AGENTS.md` if you use those agents too — fleet-config-lite doesn't auto-wire them since its own hooks/skills are Copilot-CLI-specific. Deliberately small; grow it as real corrections accumulate, don't port the private fleet-config's fleet-wide sections (multi-repo map, local LLM hub, design system, etc.) — those are out of scope here.

### Skills can come from any repo

Copilot discovers whatever sits in `~/.copilot/skills/` — the junction target is irrelevant. This repo's `skills/` is just one source; a separate team skills repo plugs in exactly the same way: junction its skill folders into `~/.copilot/skills/` (or use `copilot skill add <dir>`), and every Copilot session — including the ones App Launcher Lite's Board buttons spawn — can invoke them. `install.ps1` only ever touches junctions that point into *this* checkout, so it coexists safely with skills installed from anywhere else.

## The /e2e skill

`skills/e2e/` decides, runs, and maintains a project's end-to-end tests **proportionate to the actual diff**: a target repo declares path→tier rules in its own `.fleet.toml [e2e]` table, the bundled `classify_e2e.py` maps the changed files to `skip` / `static` / `full` (anything unmatched, malformed, or empty fails safe to `full` — uncertainty always escalates, never narrows), and the skill runs only that slice. `issue-finish` and `issue-yolo` call it before every merge request; it also runs standalone (`/e2e`, `/e2e plan`, `/e2e full`). On a repo without the router, it self-heals by copying the bundled classifier in byte-verbatim.

The folder is **fully self-contained** — no dependency on any other repo or checkout; junction it (the installer already does) and it works anywhere with Python 3.11+. Provenance: `classify_e2e.py` is vendored byte-verbatim from `project-scaffolding` `scripts/classify_e2e.py` @ `6e3b3e0` (git blob `e61e182`); re-vendor deliberately by replacing the file whole, never by editing it.

## The /learning-log skill

`skills/learning-log/` is a host-agnostic port of the private `fleet-config`'s `.claude/skills/learning-log`: on manual invocation it reads merged PRs/MRs + closed issues since the last run — across this repo and its public siblings under the same owner/group — computes exact bucketed productivity stats, fans out one insight sub-agent per work-type bucket, and upserts a ledger issue + weekly-shaped comment. `gather.py` detects whether this repo's `origin` remote is GitHub or GitLab (`git remote get-url origin`) and drives `gh` or `glab` accordingly; the GitHub path is exercised live against this repo, the GitLab path follows `glab`'s documented CLI shape but isn't live-tested here (`glab` isn't installed on this dev machine, the same caveat already accepted for this repo's other `glab`-based skills).

It is a deliberate, narrow exception to this repo's "no LLM calls" principle — the insight-extraction step is model-agnostic (never hardcodes a vendor/model name) and low-effort by design — but keeps "no schedulers": there is no unattended entry point, only `/learning-log`.

## The audit skills

Three skills port the private `fleet-config`'s `/codebase-audit` → `/audit-fleet` → `/cleanup-fleet` discipline, downscaled for a limited-credit setup: **`/codebase-audit`** reads one repo as a senior developer would and files findings into at most four living-backlog issues (`audit: bug|stale|slop|documentation findings`, one per bucket, reused across runs, max 5 new findings per bucket per run); **`/audit-fleet`** walks the sibling repos and audits at most 2 per run, sequentially; **`/cleanup-fleet <bucket>`** works one repo's bucket issue per run through this repo's own `/issue-yolo` (easy) or a build-and-stop `/issue-start` (hard). No sub-agents, no scheduler, no notifications; a security finding is reported to the terminal only and never written to an issue.

**The significance gate is what keeps it cheap.** `skills/codebase-audit/audit_gate.py gate` decides, deterministically, whether a repo deserves a read: it stores the last audited default-branch sha and rubric hash in a `codebase-audit ledger` issue (label `audit-meta`, the same block the private tool writes, so a repo audited by both keeps one ledger — this repo's is #9), then counts added+deleted lines on the mainline since that sha over **source paths only** (docs, markdown, tests and lockfiles weigh nothing) and skips commits whose message references one of the repo's own audit issues (`Closes #N`, a `<type>/N-slug` branch). Below the threshold (default 1000, `--threshold N`) the repo accumulates and the run stops before reading a file; only real growth buys a re-read, so fixing audit findings never triggers the next audit. Every unknown — no ledger, an unreachable baseline, a diff it cannot read — fails open to `AUDIT`.

```powershell
python skills\codebase-audit\audit_gate.py gate             # {"decision": "SKIP_BELOW_THRESHOLD", ...}
python skills\codebase-audit\audit_gate.py get --kind slop   # the managed issue, or number: null
```

Host is detected from `origin` like `learning-log`: the GitHub path is exercised live against this repo, the GitLab path follows `glab`'s documented CLI shape but isn't live-tested here.

## The /prompt-audit skill

`skills/prompt-audit/` is a downscaled port of the private `fleet-config`'s `.claude/skills/prompt-audit` (fleet-config#831, lite scope in #834). On manual invocation it checks whether the vendors' prompting guides moved past the vendored baselines (the session fetches each page verbatim; `audit.py diff-source` hashes it — an unfetched page is `not-checked`, never `unchanged`), lints the instruction files of this repo and its sibling repos (`global-instructions.md`, `CLAUDE.md`, `AGENTS.md`, `.github/copilot-instructions.md`, `.claude/rules/*.md`, `SKILL.md`), judges the lint candidates and judgment-only rules against `rules.md`, and posts one digest comment on a `prompt-audit ledger` issue (label `audit-meta`) in this repo. The ledger's marker, title and hidden block are the private tool's exact format, so either tool reads the other's ledger unchanged; a file whose sha is unchanged under the same rule-set hash is skipped on the next run.

Caps are hard-coded in `audit.py` and unit-tested: **at most 2 repos per run** (the rest are listed as deferred and rotate in on later runs), **at most 5 findings per file per run**, no sub-agents (the judgment pass runs serially in the invoking session), no scheduler, no notifications. Unlike the private tool it files no per-repo `prompt-drift` issues — this repo's `/cleanup-fleet` has no such bucket to consume them — and a moved guide stops the scan without filing anything here, because the rule-set is canonical upstream.

It is a deliberate, narrow exception to this repo's "no LLM calls" principle, the same carve-out as `learning-log`: the judgment step is model-agnostic (it never hardcodes a vendor or model name and runs in whichever session invoked it) while every count, hash and verdict cap comes from `audit.py`, and there is still no unattended entry point, only `/prompt-audit`.

**Port provenance.** `rules.md` and `sources.toml` are byte-identical copies, re-vendored by replacing the files whole, never by editing them here:

| File | Source | Commit | sha256 |
|---|---|---|---|
| `skills/prompt-audit/rules.md` | `fleet-config` `.claude/skills/prompt-audit/rules.md` | `ec8436d` | `19c3703c83113fd7d73d5a4756347e097e1cf7486aa8ba5ef20674b7ef852584` |
| `skills/prompt-audit/sources.toml` | `fleet-config` `.claude/skills/prompt-audit/sources.toml` | `ec8436d` | `257c77544604c3cce63f5b8c1b80fb76dc014f27414039dc605bb627eadf285b` |

The hashes are of the committed (LF) bytes; a checkout with `core.autocrlf=true` shows CRLF on disk, which `audit.py` normalises before hashing the rubric. `audit.py` itself is a self-contained near-duplicate of the private helper, not a copy.

```powershell
python skills\prompt-audit\audit.py host                  # HOST=github|CLI=gh|REPO=...
python skills\prompt-audit\audit.py plan                  # REPOS= (at most 2), PLAN=/HIT= lines, DEFERRED= repos
python skills\prompt-audit\audit.py ledger-write --run run.json --dry-run   # ARGV= lines, nothing spawned
```

Host is detected from `origin` like the other skills: the GitHub path is exercised live against this repo; the GitLab path is unit-tested with a stubbed runner (a GitLab origin drives `glab issue list/create/update/note`) but isn't live-tested here, since `glab` isn't installed on this dev machine.

## How the session hooks work

Copilot CLI fires native hooks (user scope: `~/.copilot/hooks/*.json`). The payloads are **camelCase** and carry **no event name** (verified live against CLI 1.0.70), so the rendered config passes the event as `argv[1]`:

- `userPromptSubmitted` → row status `working`
- `agentStop` → row status `needs-you` (also records `transcriptPath`)
- `sessionEnd` → row deleted (hard kills age out via a 24 h prune)
- `sessionStart` → creates an `idle` row but **never downgrades** an existing one (in `-p` mode it fires *after* `userPromptSubmitted`)

State file: `%USERPROFILE%\.copilot\hooks\state\sessions-state.json`. App Launcher Lite reads it there by default. Sessions launched from App Launcher Lite inherit `APP_LAUNCHER_SESSION_ID` / `APP_LAUNCHER_AGENT`, which the writer persists for an exact join; external sessions fall back to a cwd match.

All hooks are advisory-only: every failure is swallowed and the hook exits 0 — a broken hook can never disturb the Copilot session it observes.

## Tests

```powershell
python -m unittest discover -s tests -v
```

Stdlib only — no venv, no dependencies.

## Copilot hook gotchas (verified live, CLI 1.0.70)

**Interactive sessions may not fire hooks at all.** On CLI 1.0.70 (probed live on the original dev machine), non-interactive runs (`copilot -p ...`) fire the full sessionStart → userPromptSubmitted → agentStop → sessionEnd sequence, but an interactive TUI session (launched from App Launcher Lite with a browser terminal attached and the TUI painted) fired none of them. This matches open upstream bugs — [copilot-cli#991](https://github.com/github/copilot-cli/issues/991) (interactive sessionStart/End mis-timed), [copilot-cli#2201](https://github.com/github/copilot-cli/issues/2201) (sessionStart doesn't run at CLI startup), [copilot-cli#1730](https://github.com/github/copilot-cli/issues/1730) (repo-level hooks not firing). The writer here is correct and unit-tested; when a CLI update fixes interactive firing, the Board's session columns light up with no change on this side. Until then the Board degrades as designed: live sessions still appear (session-host presence), with status "unknown" and a "session state unavailable" note. Re-test after every `copilot update`.

The remaining failure modes are **silent** — the session runs fine, the hook just never fires:

- **No BOM.** A hook config saved as UTF-8-with-BOM is ignored. Windows PowerShell 5.1's `Set-Content -Encoding utf8` writes a BOM; the installer uses `[IO.File]::WriteAllText` (BOM-less) for exactly this reason.
- **One dot in the filename.** `foo.session-state.json` is ignored; `foo-session-state.json` loads.
- Hook configs load at CLI startup only — restart the session after installing.
- Payloads carry no event-name field; the config passes the event as `argv[1]`.

## Verifying the hooks live

1. `install.ps1`, then open a fresh Copilot session in any repo.
2. Submit a prompt → the state file shows the row as `working`.
3. Let the turn finish → `needs-you`.
4. `/exit` → the row disappears.
