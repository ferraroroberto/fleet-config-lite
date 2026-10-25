# Layout

Where code goes in this repo. The shape is `skills-governance` (declared in `.fleet.toml`); `scripts/structure_ratchet.py` holds the root folders to it and holds file size (1,000 lines), function length (100 lines) and directory width (40 modules) to the baseline in `.structure-ratchet-baseline.json`. The baseline is empty; a file nearing a limit splits into a sibling module instead of growing.

```
.fleet.toml                      architecture-map card, [vendored] table, ratchet config
install.ps1                      idempotent installer into ~/.copilot/
global-instructions.md           agent-agnostic global instructions the installer links
README.md                        index: install, run, gate, one line per feature
hooks/                           one module per Copilot hook + the shared payload helpers
hook-config/                     hook definition template the installer renders
skills/<name>/SKILL.md           one folder per skill; its helpers sit beside it
scripts/                         vendored scaffold ratchets and their gate wrappers
tests/                           stdlib unittest, one file per module under test
docs/layout.md                   this file
```

## Folders and subpackages

- `hooks/` — `session_state.py` (sole writer of the sessions state file) and `_lib.py` (payload helpers).
- `hook-config/` — `session-state.template.json`, the hook definition rendered with absolute paths.
- `skills/issue-add`, `issue-start`, `issue-finish`, `issue-yolo`, `quick` — issue-workflow skills, `SKILL.md` only.
- `skills/e2e/` — `SKILL.md`, `e2e_route.py` and the vendored `classify_e2e.py`.
- `skills/codebase-audit/` — `SKILL.md` and `audit_gate.py`; `audit-fleet` and `cleanup-fleet` are `SKILL.md` only.
- `skills/learning-log/` — `SKILL.md` and `gather.py`.
- `skills/prompt-audit/` — `SKILL.md`, `audit.py` (the entry point), `audit_lint.py` (its pure text and lint layer), `rules.md` and `sources.toml`.
- `skills/slides/` — `SKILL.md`, `assets/` and `scripts/`.
- `scripts/` — `static_ratchet.py` and `structure_ratchet.py` (vendored byte-for-byte, never edited here) and `static_ratchet_gate.py`.

## Where new code goes

- A helper used by one skill stays in that skill's folder. At its second caller it moves to `skills/_lib/`, which does not exist yet and is created by the first shared helper.
- A script that a `SKILL.md` invokes by path keeps that path.
- A new test goes in `tests/` as `test_<module>.py`. Once `tests/` nears 40 modules, new tests go in a subfolder that mirrors the code under test.

## Declared exceptions

- `hook-config/` is in `extra_roots`: the installer renders it into the Copilot hook definition, so it is data for the installer and not code under `hooks/`.
