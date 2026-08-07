"""Persist per-session state for the app-launcher-lite Board.

Maintains ``sessions-state.json`` — one row per recent Copilot CLI session
(``project``, ``status``, ``transcript_path``, ``cwd``, ``updated_at``,
``agent``, optional ``launcher_session_id``) keyed by the payload's
``session_id`` — so the Board tab can render "Bot's turn" / "Your turn"
columns without owning any hook plumbing. The Board only *reads* the file;
this module is the only writer.

Copilot CLI payloads carry no event-name field, so the hook config
(``hook-config/session-state.template.json``) passes the event name as
``argv[1]``:

* ``userPromptSubmitted`` → status ``working`` (you handed Copilot the turn).
* ``agentStop``           → status ``needs-you`` (Copilot finished a turn).
* ``sessionEnd``          → **deletes** the row (fires on clean exit only; a
  hard kill never fires it, so those rows age out via the 24h prune).
* ``sessionStart``        → upserts ``idle``, **but never downgrades an
  existing row**: in non-interactive runs Copilot fires ``sessionStart``
  *after* ``userPromptSubmitted`` (verified live, CLI 1.0.70), so an
  unconditional write would silently flip a correct ``working`` row back to
  ``idle``.

The payload's ``session_id`` is Copilot's session UUID (the same id
``copilot --resume=<id>`` accepts). App Launcher Lite injects its exact
identity as inherited ``APP_LAUNCHER_SESSION_ID`` / ``APP_LAUNCHER_AGENT``
env values; when present this writer persists them for an exact agent-aware
consumer join. External sessions keep the normalized-cwd fallback join.

Advisory-only: any failure is swallowed and the hook exits 0. The state file
lives under ``~/.copilot/hooks/state/``; ``COPILOT_HOOKS_STATE_DIR``
overrides the directory so tests stay hermetic. Rows untouched for 24h are
pruned on each write.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _lib  # noqa: E402

STATE_FILENAME = "sessions-state.json"

_PRUNE_AFTER = timedelta(hours=24)
_REPLACE_ATTEMPTS = 3  # os.replace can hit a transient PermissionError under a concurrent Windows reader

# argv[1] event name → the Board status it evidences. Anything else is ignored.
_EVENT_STATUS = {
    "userPromptSubmitted": "working",
    "agentStop": "needs-you",
    "sessionStart": "idle",
}

# sessionStart may arrive after userPromptSubmitted (see module docstring);
# it only ever fills a hole, never overwrites a real status.
_NO_OVERWRITE_EVENTS = {"sessionStart"}


def state_file() -> Path:
    """Resolve the state-file path at call time so the env override always wins."""
    root = os.environ.get("COPILOT_HOOKS_STATE_DIR")
    base = Path(root) if root else Path.home() / ".copilot" / "hooks" / "state"
    return base / STATE_FILENAME


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_updated_at(row: Any) -> Optional[datetime]:
    if not isinstance(row, dict):
        return None
    raw = row.get("updated_at")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _read_rows(path: Path) -> Dict[str, Any]:
    """Current rows, or {} on a missing/corrupt file — the writer self-heals."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_rows(path: Path, rows: Dict[str, Any]) -> None:
    """Atomic tmp+replace write, retried because a concurrent reader on Windows
    can hold the target and fail ``os.replace`` with a transient PermissionError."""
    payload = json.dumps(rows, indent=2, sort_keys=True)
    for attempt in range(_REPLACE_ATTEMPTS):
        tmp_name: Optional[str] = None
        try:
            fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            os.replace(tmp_name, path)
            return
        except OSError:
            if tmp_name:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
            time.sleep(0.05 * (attempt + 1))


def upsert_from_payload(payload: Dict[str, Any], event: str) -> None:
    """Write/refresh one session row straight from a hook payload.

    Silent no-op without a ``session_id`` or for an unmapped event.
    """
    status = _EVENT_STATUS.get(event)
    session_id = payload.get("session_id")
    if not status or not isinstance(session_id, str) or not session_id:
        return

    path = state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = _read_rows(path)

    existing = rows.get(str(session_id))
    if event in _NO_OVERWRITE_EVENTS and isinstance(existing, dict):
        # Refresh the heartbeat only; keep the stronger status.
        row = dict(existing)
        row["updated_at"] = _isoformat(_now())
        rows[str(session_id)] = row
    else:
        cwd_path = _lib.cwd(payload)
        transcript = payload.get("transcript_path")
        # Keep a transcript_path learned on a previous event (only agentStop
        # carries one) instead of erasing it on the next prompt.
        if not (isinstance(transcript, str) and transcript) and isinstance(existing, dict):
            transcript = existing.get("transcript_path")
        rows[str(session_id)] = {
            "project": cwd_path.name,
            "status": status,
            "transcript_path": transcript if isinstance(transcript, str) and transcript else None,
            "cwd": str(cwd_path),
            "name": None,
            "name_source": None,
            "agent": (
                os.environ.get("APP_LAUNCHER_AGENT", "").strip().lower() or "copilot"
            ),
            "launcher_session_id": (
                os.environ.get("APP_LAUNCHER_SESSION_ID", "").strip() or None
            ),
            "updated_at": _isoformat(_now()),
        }

    cutoff = _now() - _PRUNE_AFTER
    kept: Dict[str, Any] = {}
    for sid, row in rows.items():
        stamp = _parse_updated_at(row)
        if stamp is not None and stamp >= cutoff:
            kept[sid] = row

    _write_rows(path, kept)


def remove_from_payload(payload: Dict[str, Any]) -> None:
    """Delete the payload's session row (sessionEnd); silent no-op if absent."""
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return
    path = state_file()
    if not path.exists():
        return
    rows = _read_rows(path)
    if str(session_id) not in rows:
        return
    del rows[str(session_id)]
    _write_rows(path, rows)


def main() -> None:
    try:
        event = sys.argv[1] if len(sys.argv) > 1 else ""
        payload = _lib.read_stdin_json()
        if event == "sessionEnd":
            remove_from_payload(payload)
        else:
            upsert_from_payload(payload, event)
    except Exception:  # noqa: BLE001 — state is advisory; never disturb the session
        pass
    _lib.allow()


if __name__ == "__main__":
    main()
