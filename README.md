# fleet-config-lite

Minimal companion repo for [app-launcher-lite](https://github.com/ferraroroberto/app-launcher-lite): the GitHub-Copilot-CLI-side machinery that makes the lite Board's session columns and the issue workflow work. No LLM calls, no schedulers, no chief — just hooks, skills, and an installer. (`skills/learning-log/` is a deliberate, narrow exception to "no LLM calls" — see its own section below — and, like every skill here, is manual-invoke only.)

Downscaled from the private `fleet-config`; when a capability is missing here, port it from there deliberately rather than re-inventing it.

## What's here

| Path | Role |
|---|---|
| `hooks/session_state.py` | **Sole writer** of `sessions-state.json` — one row per live Copilot session (`working` / `needs-you` / `idle`), consumed read-only by app-launcher-lite's Board |
| `hooks/_lib.py` | Payload helpers: camelCase→snake_case normalization, stdin JSON, timestamps |
| `hook-config/session-state.template.json` | Copilot CLI hook definition (rendered with absolute paths by the installer) |
| `skills/issue-{add,start,finish,yolo}/` | Lite GitLab (`glab`) issue-workflow skills, discovered by Copilot from `~/.copilot/skills/` |
| `skills/e2e/` | Self-contained proportionate e2e skill: `SKILL.md` + `e2e_route.py` + the bundled `classify_e2e.py` router — see "The /e2e skill" below |
| `skills/quick/` | Trunk-commit lane below the issue threshold: one capped, verified commit straight to the default branch (no issue, no MR), auto-escalating to the issue workflow when the change outgrows its caps — the sanctioned exception to "never commit directly to the default branch" declared in `copilot-instructions.md` |
| `skills/learning-log/` | Host-agnostic (GitHub or GitLab) learning log + productivity stats from this repo's sibling-repo work stream: `SKILL.md` + self-contained `gather.py` — see "The /learning-log skill" below |
| `copilot-instructions.md` | Seed for the global `~/.copilot/copilot-instructions.md` |
| `install.ps1` | Wires everything into `%USERPROFILE%\.copilot\` (idempotent) |

## Install

```powershell
git clone https://github.com/ferraroroberto/fleet-config-lite
cd fleet-config-lite
powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1
```

Then restart any running Copilot CLI session (hook configs load at startup).

Requirements: Windows, Python 3.11+ on a real install path (the WindowsApps alias is rejected), GitHub Copilot CLI ≥ 1.0.70, `glab` authenticated against your GitLab host for the skills.

### Skills can come from any repo

Copilot discovers whatever sits in `~/.copilot/skills/` — the junction target is irrelevant. This repo's `skills/` is just one source; a separate team skills repo plugs in exactly the same way: junction its skill folders into `~/.copilot/skills/` (or use `copilot skill add <dir>`), and every Copilot session — including the ones App Launcher Lite's Board buttons spawn — can invoke them. `install.ps1` only ever touches junctions that point into *this* checkout, so it coexists safely with skills installed from anywhere else.

## The /e2e skill

`skills/e2e/` decides, runs, and maintains a project's end-to-end tests **proportionate to the actual diff**: a target repo declares path→tier rules in its own `.fleet.toml [e2e]` table, the bundled `classify_e2e.py` maps the changed files to `skip` / `static` / `full` (anything unmatched, malformed, or empty fails safe to `full` — uncertainty always escalates, never narrows), and the skill runs only that slice. `issue-finish` and `issue-yolo` call it before every merge request; it also runs standalone (`/e2e`, `/e2e plan`, `/e2e full`). On a repo without the router, it self-heals by copying the bundled classifier in byte-verbatim.

The folder is **fully self-contained** — no dependency on any other repo or checkout; junction it (the installer already does) and it works anywhere with Python 3.11+. Provenance: `classify_e2e.py` is vendored byte-verbatim from `project-scaffolding` `scripts/classify_e2e.py` @ `1159e30` (git blob `1ec97cf`); re-vendor deliberately by replacing the file whole, never by editing it.

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
