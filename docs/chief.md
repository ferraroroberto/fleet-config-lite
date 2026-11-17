# The lite fleet chief: helpers

app-launcher-lite carries the launcher side of the fleet chief (the plan and journal cards, the mailbox, the doorbell, the dispatch brief). This repo carries the helper side: the code the chief session runs and the state files the launcher reads. Every state file keeps the full `fleet-config` format byte for byte, so app-launcher-lite's readers parse it unchanged; only the location moves, from `~/.claude/hooks/state/` to `~/.copilot/hooks/state/`.

## Entry point

The chief calls one CLI, `skills/_lib/chief_ops.py`, and acts only on the `KEY=value` lines it prints to stdout. Breadcrumbs go to stderr. A refused write exits 2 with `ERROR: ...` on stderr and leaves the state file as it was.

```powershell
python skills\_lib\chief_ops.py plan show
python skills\_lib\chief_ops.py plan add <repo>#<N> "<title>" [--status S] [--model M] [--kind K]
python skills\_lib\chief_ops.py plan lane <repo> building|gate|idle|waiting [--item "#N"]
python skills\_lib\chief_ops.py plan ask "<question>" --ref <repo>#<N> --option "Label::why" ...
python skills\_lib\chief_ops.py plan prune             # drop merged rows
python skills\_lib\chief_ops.py note "<one line>" [--kind K] [--ref <repo>#<N>]
```

| Subcommand | Writes | Read by (app-launcher-lite) |
|---|---|---|
| `plan ...` | `chief-plan.json`, format v1; each transition also journalled | `src/chief/plan.py`, `src/chief/queue_status.py`; `src/chief/plan_prune.py` loads `chief_plan.py` by path and calls `prune_plan_file` |
| `note ...` | `chief-journal.jsonl`, one JSON line per event, beside the plan file | `src/chief/journal.py` |

The state directory is `~/.copilot/hooks/state/`, or `COPILOT_HOOKS_STATE_DIR` when set (the same override `hooks/session_state.py` honours). `skills/_lib/fleet_core/hooks_state.py` is the one place that resolves it.

## Port provenance

These files are byte-identical copies of `fleet-config`'s `skills/_lib/` at commit `173b70a`, re-vendored by replacing the file whole, never by editing it here. `tests/test_chief_port.py` fails when one drifts from its hash. The hashes are of the LF bytes; a CRLF checkout is normalised before hashing.

| File | sha256 |
|---|---|
| `skills/_lib/chief_plan.py` | `24dd104adc2fd3e51dee7d5bdbdb780bd9284753cfc4ec2b79f13422946fec84` |
| `skills/_lib/chief/plan_cli.py` | `e6371d1e67093cd6edf623a41ba46db14644d5c0cc6218de4ffd3d058a8a65e0` |
| `skills/_lib/chief/journal.py` | `cada1e732a0b4f5213af2c336141771a3bf493a4f52185bc6775bfe4d3125c40` |
| `skills/_lib/chief/__init__.py` | `4374263a66818558e16a1b08fda0ae11ec96fe28e18315df5502f4298d2b3e16` |
| `skills/_lib/active_issue.py` | `4ca4b864e1cf95bdd73154566266ba3ad8739663a4f4448486cf928c937990d7` |
| `skills/_lib/git_run.py` | `22c69832c10b3321553394db35964a119dbeb1a2dc6008b1d24d8a8c25efba04` |
| `skills/_lib/worktree_residue.py` | `08243734d28a8d5957f2d57417facc2274a07484dc213f24918a0c2c4e36a144` |
| `skills/_lib/no_window.py` | `a2a46223f213908fbfad75e9544f136b7c8a08ec5a5f274f62a885c796e998d7` |
| `skills/_lib/fleet_core/__init__.py` | `19f21ca16675ba975cd8aaa8f3ca19a575d4f0057593bf1efe5528ad8e8d820c` |
| `skills/_lib/fleet_core/runtime_files.py` | `b25bd8e88f69993cb83a205b37362eb189dba22bc2321d04f34809a7bf52c7b6` |

Lite-specific, not copies: `skills/_lib/chief_ops.py`, which mounts only the subcommands this tree carries, and `skills/_lib/fleet_core/hooks_state.py`, which differs from upstream only in the Copilot state directory and its override variable. The ported docstrings still name `~/.claude/hooks/state/` and `CLAUDE_HOOKS_STATE_DIR`. Behaviour follows `hooks_state.py`, not that wording.

## Not carried yet

A queue row parked with `--kind owner` needs the `needs-owner` label check from `owner_check`, which this tree does not carry yet. Until it does, that write is refused with `ERROR: not available in this checkout` and nothing is written. `--kind umbrella` and `--kind 'blocked-by <repo>#<N>'` work.
