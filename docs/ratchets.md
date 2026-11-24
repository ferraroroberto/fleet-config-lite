# Ratchets

Per-ratchet specifics for the twelve vendored baseline-and-ratchet quality gates
listed in the root [README.md](../README.md)'s "The ratchets" table. The
mechanics shared by all twelve — vendoring, the never-shrinks-except-by-review
baseline, exit 3 always failing as NOT CONFIRMED — are stated once there; this
page only carries what differs per ratchet.

## static

Prerequisites, both on the machine that runs the tests:

- **ruff** from `requirements-dev.txt`, importable by the interpreter that
  runs the tests (`python -m ruff`).
- **Node (`npx`)** for `jscpd`; its first run downloads the pinned release, so
  it needs network once.

No duplicate is carved out of the ratchet: the remote-URL, managed-issue marker
and gh/glab issue helpers the audit and learning-log scripts once copied live
once in `skills/_lib/issue_host.py`, per the `layout.md` rule that a second
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
unused API is not reported as this repo's own dead code. Skill scripts are
plain functions called by name, so no `entry_decorators` is configured and
`allow` is empty. The baseline is empty.

## conventions

Enabled rules: `no-window` (skills spawn processes on Windows),
`logging-not-print` (scoped to `skills/`, the library code) and
`no-drive-path` (nothing here may name a machine's drive) and
`subprocess-timeout` (a `subprocess.run/call/check_call/check_output` passes
`timeout=`, or carries a `# subprocess-timeout-exempt: <reason>` marker for a
child that is meant to run unbounded) and `browser-per-iteration` (a Playwright
browser or context opened inside a loop) and `host-identity` (a test reads the real
account name or home folder, which passes on this machine and fails on another host; a
test sets `HOME`/`USERPROFILE` to a temp folder and compares against that, or carries a
`# host-identity-exempt: <reason>` marker for a guard over the live install) and `git-wrapper` (every `git` spawn goes
through `skills/_lib/git_run.py`, which sets `GIT_OPTIONAL_LOCKS=0`). `secret-compare`
stays off — the repo has no secret-compare helper for it to route through. There is no `[e2e]` router table, so the baseline file
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
(a deck dir, `--out-dir`) is written through
`skills/_lib/runtime_files.py`, which raises when the resolved path is under a code folder, so the
guarantee is checked at runtime instead of claimed per call.
The script's `--snapshot`/`--probe` pair is not wired: the tests are the gate
run itself, so there is no stage outside them to bracket.

## request budget

Vendored with its sibling `scripts/request_budget_scan.py`, which holds the readers. This repo
serves no HTTP and carries no browser code under the default `browser_paths`, so the poll
rules (`fixed-rate-poll`, `poll-floor`), `timing-middleware` and `scan-per-request` have
nothing to read: `scan-per-request` prints OFF because no `handler_dirs` is declared, and the
scaffold's poll helper and timing middleware are not vendored. `server_paths` covers `skills/` and `scripts/`, the Python this repo ships.
The baseline is empty and no loop is declared under `[[request_budget.loops]]`. A bounded wait
that must run unwatched is declared there with its path, function, interval and reason.

## port host

Vendored with its sibling `scripts/ratchet_baseline.py`, which keeps the baseline in `.ratchets/port-host.json`. This repo serves nothing and reads no port, so no `resolvers` are declared and the baseline is empty. A port or machine-local host written in the tracked scripts or code is a hit; a file that comes to own port defaults is listed under `resolvers` before the baseline is touched, and the ports are read from its config instead. A hit that must stay carries a `port-host-exempt: <reason>` marker, printed on every run.

## clean tree

Vendored with the same `scripts/ratchet_baseline.py`; the baseline is `.ratchets/clean-tree.json`. This repo serves nothing, so the smoke is a command: Windows PowerShell runs `install.ps1 -SkipVenv -SkipChecklist` once, with `COPILOT_HOME` exported as the run's scratch folder and `USERPROFILE` set to the same folder inside the command. The profile is moved as well because the installer reads `~/.agents/skills` to detect a shared machine, and on a machine that also runs the full fleet that check would skip every write and leave the smoke empty. With both moved, the instructions copy and the skill junctions land in the scratch folder, so the real Copilot home is never touched, and the ratchet removes the scratch folder afterwards. The baseline is empty: the installer writes nothing under the checkout. A smoke that cannot start, times out or exits non-zero is exit 3, NOT CONFIRMED. The stage needs Windows PowerShell on the machine that runs the tests, like the installer itself.
