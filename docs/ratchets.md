# Ratchets

Per-ratchet specifics for the eight vendored baseline-and-ratchet quality gates
listed in the root [README.md](../README.md)'s "The ratchets" table. The
mechanics shared by all eight — vendoring, the never-shrinks-except-by-review
baseline, exit 3 always failing as NOT CONFIRMED — are stated once there; this
page only carries what differs per ratchet.

## static

Prerequisites, both on the machine that runs the tests:

- **ruff** from `requirements-dev.txt`, importable by the interpreter that
  runs the tests (`python -m ruff`).
- **Node (`npx`)** for `jscpd`; its first run downloads the pinned release, so
  it needs network once.

One duplicate is intentional and declared in the source instead of the
baseline: `parse_owner_repo` and `detect_host` in
`skills/codebase-audit/audit_gate.py` sit between `jscpd:ignore-start` and
`jscpd:ignore-end` markers (the copy in `skills/prompt-audit/audit.py` stays
unmarked), because each skill folder is junctioned into `~/.copilot/skills/`
on its own and must work with no import across skills, so deduplicating would
couple them. `scripts/static_ratchet_gate.py` maps the script's exit codes (0
pass; 1 new finding; 2 bad config; 3 detector could not run). The ratchet
tests share one assertion, `assert_ratchet_passes` in
`tests/test_structure_ratchet.py`.

## structure

Shape is `skills-governance`; where new code goes:
[layout.md](layout.md).

## instruction

Configured with `skill_dirs = ["skills"]`; this repo has no `CLAUDE.md` or
`AGENTS.md` to scan.

## doc-refs

No `port` is declared, so ports are not checked. `allow_refs` lists one
intentional pointer — the shared-helper folder `layout.md` says the first
shared helper creates.

## dead-code

Every vendored file is declared in `.fleet.toml`'s `[vendored]` table, so its
unused API is not reported as this repo's own dead code. Hooks and skill
scripts are plain functions called by name, so no `allow` or
`entry_decorators` is configured.

## conventions

Enabled rules: `no-window` (hooks and skills spawn processes on Windows),
`logging-not-print` (scoped to `hooks/` and `skills/`, the library code) and
`no-drive-path` (nothing here may name a machine's drive). `secret-compare`
and `git-wrapper` stay off — the repo has no secret-compare or git helper for
them to route through. There is no `[e2e]` router table, so the baseline file
needs no `tier` rule.

## docs

`README.md` is under the 40 KiB budget today.

## comment

Every vendored destination is excluded automatically, since the ratchet only
scans tracked, non-vendored files.
