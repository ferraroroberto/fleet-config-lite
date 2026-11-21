# Layout

Where code goes in this repo. The shape is `skills-governance` (declared in `.fleet.toml`); `scripts/structure_ratchet.py` holds the root folders to it and holds file size (1,000 lines), function length (100 lines) and directory width (40 modules) to the baseline in `.structure-ratchet-baseline.json`. The baseline is empty; a file nearing a limit splits into a sibling module instead of growing.

```
.fleet.toml                      architecture-map card, [vendored] table, ratchet config
install.ps1                      idempotent installer into ~/.copilot/
global-instructions.md           agent-agnostic global instructions the installer links
README.md                        index: install, run, gate, one line per feature
hooks/                           one module per Copilot hook, the shared payload helpers and the hook definition template the installer renders
skills/<name>/SKILL.md           one folder per skill; its helpers sit beside it
.github/skills/chief/SKILL.md    the chief skill, a project skill loaded only in this checkout
scripts/                         vendored scaffold ratchets, their gate wrappers and copilot_probe.py
tests/                           stdlib unittest, one file per module under test
docs/layout.md                   this file
```

## Folders and subpackages

- `hooks/` — `session_state.py` (sole writer of the sessions state file), `chief_inbox.py` (the chief's mailbox writer it calls), `chief_guard.py` and `chief-guard.template.json` (the chief's guard hooks), `_lib.py` (payload helpers) and `session-state.template.json`, the hook definition the installer renders with absolute paths.
- `skills/issue-add`, `issue-start`, `issue-finish`, `issue-yolo`, `quick` — issue-workflow skills, `SKILL.md` only.
- `skills/_lib/` — `runtime_files.py`, the flat import name for the ported `fleet_core/runtime_files.py` guarded writer that the e2e, learning-log and slides scripts share (a re-export, so the guarded-folder set is defined once), `glab_run.py`, the one place `glab` is spawned and its error ladder and JSON read live (the chief, the owner check and `launcher.py` all call it), `gitlab_git_access.py`, the check behind install.ps1's "git reaches GitLab without a prompt" line, and `issue_host.py`, the remote-URL parser, managed-issue marker and gh/glab issue argv the codebase-audit, prompt-audit and learning-log scripts share. It also holds the chief helpers: `chief_ops.py` (the chief's CLI), `chief_plan.py`, `chief_managed.py` and the `chief/` package, with the closure they import (`active_issue.py`, `git_run.py`, `worktree_residue.py`, `no_window.py`, `fleet_core/`, `owner_check/`, `worktree_claim.py`, `worktree/`, `untrack_guard.py`), byte-identical ports listed in [chief.md](chief.md).
- `skills/e2e/` — `SKILL.md`, `e2e_route.py` and the vendored `classify_e2e.py`.
- `skills/codebase-audit/` — `SKILL.md` and `audit_gate.py`; `audit-fleet` and `cleanup-fleet` are `SKILL.md` only.
- `skills/learning-log/` — `SKILL.md` and `gather.py`.
- `skills/prompt-audit/` — `SKILL.md`, `audit.py` (the entry point), `audit_lint.py` (its pure text and lint layer), `rules.md` and `sources.toml`.
- `skills/slides/` — `SKILL.md`, `assets/` and `scripts/`.
- `scripts/` — `static_ratchet.py` and `structure_ratchet.py` (vendored byte-for-byte, never edited here) and `static_ratchet_gate.py`; `copilot_probe.py`, the Copilot CLI capability probe run by hand after each CLI update.

## Where new code goes

- A helper used by one skill stays in that skill's folder. At its second caller it moves to `skills/_lib/`. A script reaches it through its real (resolved) path, so the junction layout of `~/.copilot/skills/` does not matter.
- A script that a `SKILL.md` invokes by path keeps that path.
- A new test goes in `tests/` as `test_<module>.py`. Once `tests/` nears 40 modules, new tests go in a subfolder that mirrors the code under test.
