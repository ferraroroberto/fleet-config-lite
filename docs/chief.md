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
python skills\_lib\chief_ops.py inbox [--count]     # claim pending mailbox events
python skills\_lib\chief_ops.py ack <id> [<id> ...]  # retire handled events
python skills\_lib\chief_managed.py mark <sid> <repo> <number>
python skills\_lib\chief_ops.py board | sessions | chief-sid
python skills\_lib\chief_ops.py dispatch <repo> <N> [--mode start|yolo] [--model M] [--brief-file F]
python skills\_lib\chief_ops.py say <sid> --file brief.md --verify
python skills\_lib\chief_ops.py exchange <sid> | stop <sid> [--kill]
python skills\_lib\chief_ops.py issues <repo>#<N> ...
python skills\_lib\chief_ops.py verify <repo> --expect mr-open|merged [--branch B]
```

Launcher calls go to app-launcher-lite on `http://127.0.0.1:8465` (`--base-url` overrides; any non-loopback host is refused). A launcher that stays silent prints `UNCONFIRMED=...` and one that refuses the connection prints `UNREACHABLE=...`; neither is folded into a verdict. Forge reads go through `glab` against `<owner>/<repo>` on GitLab (`--owner`, default `ferraroroberto`). When `glab` is missing or signed out, `issues` prints an `error:` row for the ref and `verify` prints `STATUS=UNKNOWN`.

`dispatch` keeps fleet-config's rails verbatim (`chief/rails.py`). It refuses before the POST if the repo is occupied, the worker cap is reached, a yolo is unconfirmed, the issue carries `needs-owner`, or a fleet-wide brief would run while a fleet-wide Job is running. A spawn the launcher may still be running prints `DISPATCH=unconfirmed` and must not be retried. `--model` is a Copilot model id, sent to the launcher as typed.

`verify` is lite's own: the lane ships through a GitLab merge request, so `--expect mr-open` means a clean checkout plus an open merge request from the branch, and `--expect merged` means a clean checkout back on the default branch plus a merged one. It prints the same `STATUS=CLEAN|DIRTY|UNKNOWN`, `BRANCH=` and `REASON=` lines as upstream.

| Subcommand | Writes | Read by (app-launcher-lite) |
|---|---|---|
| `plan ...` | `chief-plan.json`, format v1; each transition also journalled | `src/chief/plan.py`, `src/chief/queue_status.py`; `src/chief/plan_prune.py` loads `chief_plan.py` by path and calls `prune_plan_file` |
| `note ...` | `chief-journal.jsonl`, one JSON line per event, beside the plan file | `src/chief/journal.py` |
| `inbox`, `ack` | claims events into `chief-inbox/.claimed/`, deletes them on ack | the chief itself; the launcher publishes `session-end`, `job-failed`, `cap-raised` and other events into the same directory |
| `chief_managed.py mark` | `chief-managed.json`, one row per chief-dispatched launcher session | called by the launcher's `POST /api/board/issues/start` through `<this repo>/.venv/Scripts/python.exe`; read by `hooks/chief_inbox.py` and the launcher's reaper (`src/chief_session_end.py`) |

The state directory is `~/.copilot/hooks/state/`, or `COPILOT_HOOKS_STATE_DIR` when set (the same override `hooks/session_state.py` honours). `skills/_lib/fleet_core/hooks_state.py` is the one place that resolves it.

## The mailbox

A worker the chief dispatched has its launcher session id in `chief-managed.json`. On that worker's `agentStop` and `sessionEnd`, `hooks/chief_inbox.py` (called from `hooks/session_state.py` on the same hook invocation) publishes one event file into `chief-inbox/`, in fleet-config's mailbox v2 format: `kind` `turn-end` or `session-end`, `event` `Stop` or `SessionEnd`, the registry row's `repo`, `number` and `dispatch_id`. Every other session returns before any I/O. A second `turn-end` from one session within 45 s is not written. An unreadable registry writes nothing and logs that the state was undetermined.

Copilot's `agentStop` payload carries no reply text, only `transcriptPath`, the session's `events.jsonl`. The excerpt is therefore the newest `assistant.message` content in the last 256 KiB of that file (`excerpt_source: transcript`, at most 1,500 characters). The `busy` flag upstream sets from the process table is never written here, which the contract allows: an absent flag means unknown.

Not carried: upstream skips a nested print-mode child (a `claude -p` a lane starts) that inherits the lane's `APP_LAUNCHER_SESSION_ID`. Copilot exposes no entrypoint marker for that, so a `copilot -p` run from inside a chief-managed lane still writes events as the lane. The chief dedupes by `id` and reads the exchange, so the cost is a spurious wake.

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
| `skills/_lib/chief_managed.py` | `225b2fa8b39786916ae3cd0eca0e1cf983191bc07bd9db4f6f513031294f2dc2` |
| `skills/_lib/chief/mailbox.py` | `50c0498fb8edb3f2b99bd92bf328fa6ca377b11e98659804dbfd7e8fe2129a79` |
| `skills/_lib/chief/digest.py` | `152d2db0e73381b17ac77905376ba6d1b197f7f322625874e28182ef0addfd29` |
| `skills/_lib/chief/rails.py` | `8608a2ff8b7f4dbc00224fbaa943d165b2cd8a38e04d725f98c1d1ab3f5638bf` |
| `skills/_lib/owner_check/block.py` | `bf896b68ba15c6cab78b51e60cb9b5e778130ae87bfbbbffbad501642074e198` |
| `skills/_lib/fleet_core/fleet_repo_scan.py` | `038aa50e37a105e07dfb4e360d86702804e2ec009cc5b8a6e292416c7b5b656f` |
| `skills/_lib/chief/steer_delivery.py` | `164f17148fbcc86f4c9ae776f189c4d2bb18c439a85e9d8428f4b8243e7e5dae` |

Lite-specific, not copies: `skills/_lib/chief_ops.py`, which mounts only the subcommands this tree carries; `skills/_lib/chief/lite_commands.py`, `lite_lanes.py` and `lite_verify.py`, its handlers (`lite_lanes.py` keeps upstream's `chief/commands.py` bodies; only the grokbot line, the Codex catalog and the Telegram escalation are gone); `skills/_lib/chief/launcher.py`, upstream's copy with three seams changed: the lite base URL, `glab` for issue state, and no Codex catalog; `skills/_lib/owner_check/__init__.py`, which exposes only `block`; `hooks/chief_inbox.py`, the mailbox writer for Copilot's payloads; and `skills/_lib/fleet_core/hooks_state.py`, which differs from upstream only in the Copilot state directory and its override variable. The ported docstrings still name `~/.claude/hooks/state/` and `CLAUDE_HOOKS_STATE_DIR`. Behaviour follows `hooks_state.py`, not that wording.

## Not carried yet

A queue row parked with `--kind owner` needs the `needs-owner` label check from `owner_check`, which this tree does not carry yet. Until it does, that write is refused with `ERROR: not available in this checkout` and nothing is written. `--kind umbrella` and `--kind 'blocked-by <repo>#<N>'` work.
