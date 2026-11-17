"""Deterministic operations helper for the lite fleet chief (Copilot CLI).

The lite counterpart of fleet-config's `chief_ops.py`: one CLI the chief calls
instead of retyping board, plan and session operations. The modules behind
each subcommand are byte-identical ports of fleet-config's `skills/_lib/chief/`
wherever the format is shared with app-launcher-lite's readers; the state they
write lives under `~/.copilot/hooks/state/` (`fleet_core/hooks_state.py`,
override `COPILOT_HOOKS_STATE_DIR`).

Subcommands
-----------
  plan [--plan-file PATH] show|lane|drop-lane|add|set|move|remove|prune|wait|ask|unwait|clear ...
      The chief's structured plan, `chief-plan.json` format v1 (`chief_plan.py`
      is its only writer; `chief/plan_cli.py` the argv). Each transition is
      journalled beside the plan file.

  note <text> [--kind K] [--ref <repo>#<N>] [--journal-file PATH]
      Append one line to `chief-journal.jsonl` for the Board's "since you
      last looked" card (`chief/journal.py`).

  inbox [--count [--older-than SECS]] [--stale-after SECS]
      Mailbox v2 reader (`chief/mailbox.py`): re-offers claims unacked for
      `--stale-after` (default 900 s), then claims every pending event into
      `chief-inbox/.claimed/` and prints the batch (`INBOX=events n=N ...`, one
      block per event, then `ACK=`), or `INBOX=empty`. Nothing is deleted until
      `ack`. `--count` claims nothing and prints `PENDING=<n>`
      (`PENDING=unknown` and exit 1 when the directory can't be listed).

  ack <id> [<id> ...]
      Retires handled events. `ACKED=<n>`, plus `ACK_MISSING=<id>` and exit 1
      for an id with no file.

stdout carries the `KEY=value` result lines the chief acts on; breadcrumbs go to
stderr. Exit 2 with `ERROR: ...` on stderr for a refused write.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from chief import journal, lite_commands, plan_cli  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    """The lite `chief_ops` parser: every subcommand this tree carries so far."""
    parser = argparse.ArgumentParser(prog="chief_ops", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    journal.add_parser(sub)
    plan_cli.add_cli(sub.add_parser("plan", help="read or change the chief's plan"))
    lite_commands.add_mailbox_parsers(sub)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    # Breadcrumbs go to stderr, so every command's stdout format is unchanged.
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        return args.func(args)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except ImportError as exc:
        # A verb whose helper this lite tree does not carry yet (e.g. `--kind owner`
        # needs owner_check): refused before anything is written.
        print(f"ERROR: not available in this checkout: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
