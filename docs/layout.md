# Layout

Where code goes in this repo. The Copilot hooks, the chief and the lane skills live in app-launcher-lite's `copilot/` folder, not here. The shape is `skills-governance` (declared in `.fleet.toml`); `scripts/structure_ratchet.py` holds the root folders to it and holds file size (1,000 lines), function length (100 lines) and directory width (40 modules) to the baseline in `.ratchets/structure.json`. The baseline is empty; a file nearing a limit splits into a sibling module instead of growing.

```
.fleet.toml                      architecture-map card, [vendored] table, ratchet config
install.ps1                      idempotent installer into ~/.copilot/
global-instructions.md           agent-agnostic global instructions the installer links
README.md                        index: install, run, gate, one line per feature
skills/<name>/SKILL.md           one folder per skill; its helpers sit beside it
scripts/                         vendored scaffold ratchets and helpers, plus the static gate wrapper
.ratchets/<name>.json            one committed baseline per ratchet
tests/                           stdlib unittest, one file per module under test
docs/layout.md                   this file
docs/ratchets.md                 what differs per ratchet
docs/slides-adoption.md          moving a computer's existing decks onto the slides catalog
```

## Folders and subpackages

- `skills/_lib/` — `runtime_files.py`, the flat import name for the ported `fleet_core/runtime_files.py` guarded writer that the learning-log and slides scripts share (a re-export, so the guarded-folder set is defined once), `git_run.py`, the one place `git` is spawned, `no_window.py`, and `issue_host.py`, the remote-URL parser, managed-issue marker and gh/glab issue argv the codebase-audit, prompt-audit and learning-log scripts share.
- `skills/codebase-audit/` — `SKILL.md` and `audit_gate.py`; `audit-fleet` and `cleanup-fleet` are `SKILL.md` only.
- `skills/learning-log/` — `SKILL.md` and `gather.py`.
- `skills/prompt-audit/` — `SKILL.md`, `audit.py` (the entry point), `audit_lint.py` (its pure text and lint layer), `rules.md` and `sources.toml`.
- `skills/slides/` — `SKILL.md`, `assets/` and `scripts/`; `skills/slides/assets/catalog.json` is generated from `skills/slides/assets/components.md` by `skills/slides/scripts/build_catalog.py` and never hand-edited.
- `scripts/` — every ratchet and ratchet helper in `.fleet.toml`'s `[vendored]` table (vendored byte-for-byte, never edited here), and `static_ratchet_gate.py`, the gate wrapper around `static_ratchet.py`.

## Where new code goes

- A helper used by one skill stays in that skill's folder. At its second caller it moves to `skills/_lib/`. A script reaches it through its real (resolved) path, so the junction layout of `~/.copilot/skills/` does not matter.
- A script that a `SKILL.md` invokes by path keeps that path.
- A new test goes in `tests/` as `test_<module>.py`. Once `tests/` nears 40 modules, new tests go in a subfolder that mirrors the code under test.
