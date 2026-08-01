# Global instructions (work)

Seed for `%USERPROFILE%\.copilot\copilot-instructions.md` — copy or merge these
into that file (Copilot CLI reads it in every session). Deliberately small;
grow it as real corrections accumulate.

## Working method

- Non-trivial changes start with a short plan (files to touch, approach,
  risks); one-line fixes don't.
- Ask before assuming: file/module location for new code, data shapes, error
  handling, and whether to add tests. One sharp question beats three filler ones.
- Re-read a file before modifying it. Reproduce a bug before fixing it.
- Verify with the project's actual tooling (tests, lint, byte-compile) before
  declaring done. If no checker exists, say so — never claim "tests pass"
  when there are no tests. Report failures faithfully.

## Conventions

- Read the README first — layout is documented per project, never assumed.
- Config in the project's declared config file; secrets never committed.
- Python: snake_case files/functions, PascalCase classes, UPPER_CASE
  constants; type hints on public functions; `logging`, not `print()`.
- Implement only what was asked. Three similar lines beat a premature
  abstraction.

## Git discipline

- Never commit or push without being asked — prepare a ready-to-copy
  conventional commit message (`type: subject`, ≤72-char first line, body
  bullets explaining *why*).
- One issue → one branch (`<type>/<N>-<slug>`) → one MR (`Closes #N`) →
  squash-merge → branch deleted. Never commit directly to the default branch.
- No AI attribution trailers in commit messages.

## Issue workflow

`/issue-add` (file it), `/issue-start N` (branch + context), `/issue-finish`
(gate + MR + merge), `/issue-yolo N` (end-to-end, no plan gate, gate still
mandatory) — installed from this repo's `skills/` by `install.ps1`.
