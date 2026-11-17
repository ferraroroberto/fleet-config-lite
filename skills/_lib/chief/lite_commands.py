"""The lite `chief_ops.py` subcommands that are not byte-identical ports.

fleet-config's `chief/commands.py` wires every handler to the full launcher and
`gh`; the lite chief runs on Copilot CLI and GitLab, so its handlers live here
and call the ported decision modules (`mailbox`, `rails`, `digest`) unchanged.
Each handler prints the same `KEY=value` lines as its fleet-config counterpart.
"""

from __future__ import annotations

import argparse

from . import mailbox


def cmd_inbox(args: argparse.Namespace) -> int:
    """Mailbox v2: claim the pending batch for handling, or just count it."""
    inbox = mailbox.chief_inbox_dir()
    if args.count:
        try:
            print(f"PENDING={mailbox.count_pending(inbox, stale_after=args.stale_after, older_than=args.older_than)}")
        except OSError as exc:
            print(f"PENDING=unknown reason={type(exc).__name__}: {exc}")
            return 1
        return 0
    events, reoffered, dropped = mailbox.claim_mailbox(inbox, stale_after=args.stale_after)
    print(mailbox.format_mailbox_batch(events, reoffered, dropped, stale_after=args.stale_after))
    return 0


def cmd_ack(args: argparse.Namespace) -> int:
    """Retire handled events by id; exit 1 when an id has no file."""
    acked, missing = mailbox.ack_events(mailbox.chief_inbox_dir(), args.ids)
    print(f"ACKED={len(acked)}")
    for event_id in missing:
        print(f"ACK_MISSING={event_id}")
    return 1 if missing else 0


def add_mailbox_parsers(sub: argparse._SubParsersAction) -> None:
    """Mount `inbox` and `ack` with fleet-config's argv."""
    ib = sub.add_parser("inbox", help="mailbox v2: claim the pending batch, or --count it")
    ib.add_argument("--count", action="store_true", help="print PENDING=<n> and claim nothing")
    ib.add_argument("--stale-after", type=float, default=mailbox.CLAIM_STALE_SECONDS,
                    help="seconds before an unacked claim is re-offered")
    ib.add_argument("--older-than", type=float, default=0.0,
                    help="with --count: count only events that have waited at least this many seconds")
    ib.set_defaults(func=cmd_inbox)

    ak = sub.add_parser("ack", help="mailbox v2: retire handled events by id")
    ak.add_argument("ids", nargs="+")
    ak.set_defaults(func=cmd_ack)
