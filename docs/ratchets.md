# Ratchets

Per-ratchet specifics for the nine vendored baseline-and-ratchet quality gates
listed in the root [README.md](../README.md)'s "The ratchets" table. The
mechanics shared by all nine — vendoring, the never-shrinks-except-by-review
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
unmarked), because both audit scripts import nothing from `skills/_lib/` or from each
other, so each runs from its own folder alone; deduplicating would couple
them. This is a declared exception to the `layout.md` rule that a second
caller moves a helper to `skills/_lib/`. `scripts/static_ratchet_gate.py` maps the script's exit codes (0
pass; 1 new finding; 2 bad config; 3 detector could not run). The ratchet
tests share one assertion, `assert_ratchet_passes` in
`tests/test_structure_ratchet.py`.

## structure

Shape is `skills-governance`; where new code goes:
[layout.md](layout.md).

## instruction

Configured with `skill_dirs = ["skills"]`; this repo has no `CLAUDE.md` or
`AGENTS.md` to scan. `ci_expectations`, `claude_md_max_lines = 120` and
`repeated_text_words = 12` are on, at zero. `agents_pointer` is off: it needs an
`AGENTS.md` pointing at a `CLAUDE.md`, and this repo has neither.

## doc-refs

No `port` is declared, so ports are not checked.

## dead-code

Every vendored file is declared in `.fleet.toml`'s `[vendored]` table, so its
unused API is not reported as this repo's own dead code. Hooks and skill
scripts are plain functions called by name, so no `allow` or
`entry_decorators` is configured.

## conventions

Enabled rules: `no-window` (hooks and skills spawn processes on Windows),
`logging-not-print` (scoped to `hooks/` and `skills/`, the library code) and
`no-drive-path` (nothing here may name a machine's drive) and
`subprocess-timeout` (a `subprocess.run/call/check_call/check_output` passes
`timeout=`, or carries a `# subprocess-timeout-exempt: <reason>` marker for a
child that is meant to run unbounded). `secret-compare`
and `git-wrapper` stay off — the repo has no secret-compare or git helper for
them to route through. There is no `[e2e]` router table, so the baseline file
needs no `tier` rule.

## docs

`README.md` is under the 40 KiB budget today.

## comment

Every vendored destination is excluded automatically, since the ratchet only
scans tracked, non-vendored files. `docstrings` and `history_phrases` are on, at
zero, so a docstring states the present-tense why too.

## runtime write

Vendored with its sibling `scripts/runtime_write_resolve.py`, which the script
imports. The default code folders apply. The baseline is empty and no `# runtime-write-exempt` marker sits
outside the vendored scripts and the two in the guarded writer. A destination a caller names
(a deck dir, `--out-dir`, the repo an e2e bootstrap targets) is written through
`skills/_lib/runtime_files.py`, which raises when the resolved path is under a code folder, so the
guarantee is checked at runtime instead of claimed per call.
The script's `--snapshot`/`--probe` pair is not wired: the tests are the gate
run itself, so there is no stage outside them to bracket.
