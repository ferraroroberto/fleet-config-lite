"""Hermetic tests for hooks/session_state.py (stdlib unittest, no deps).

Run:  python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1] / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import _lib  # noqa: E402
import session_state  # noqa: E402


def _payload(sid: str = "abc-123", **extra):
    base = {
        "sessionId": sid,
        "timestamp": 1785613387578,
        "cwd": "C:\\work\\some-project",
    }
    base.update(extra)
    return _lib.normalize_payload(base)


class SessionStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["COPILOT_HOOKS_STATE_DIR"] = self._tmp.name
        os.environ.pop("APP_LAUNCHER_SESSION_ID", None)
        os.environ.pop("APP_LAUNCHER_AGENT", None)

    def tearDown(self) -> None:
        os.environ.pop("COPILOT_HOOKS_STATE_DIR", None)
        self._tmp.cleanup()

    def _rows(self):
        return json.loads(session_state.state_file().read_text(encoding="utf-8"))

    # ---- normalization -----------------------------------------------------

    def test_normalize_camelcase_payload(self):
        p = _payload(prompt="hi", transcriptPath="C:\\t\\events.jsonl")
        self.assertEqual(p["session_id"], "abc-123")
        self.assertEqual(p["transcript_path"], "C:\\t\\events.jsonl")
        self.assertEqual(p["cwd"], "C:\\work\\some-project")

    def test_normalize_passthrough_for_snake_case(self):
        original = {"session_id": "x", "cwd": "C:\\y"}
        self.assertIs(_lib.normalize_payload(original), original)

    # ---- event → status ----------------------------------------------------

    def test_prompt_writes_working_row(self):
        session_state.upsert_from_payload(_payload(prompt="go"), "userPromptSubmitted")
        row = self._rows()["abc-123"]
        self.assertEqual(row["status"], "working")
        self.assertEqual(row["project"], "some-project")
        self.assertEqual(row["agent"], "copilot")
        self.assertIsNone(row["launcher_session_id"])
        self.assertTrue(row["updated_at"].endswith("Z"))

    def test_agent_stop_writes_needs_you_with_transcript(self):
        session_state.upsert_from_payload(
            _payload(transcriptPath="C:\\t\\events.jsonl", stopReason="end_turn"),
            "agentStop",
        )
        row = self._rows()["abc-123"]
        self.assertEqual(row["status"], "needs-you")
        self.assertEqual(row["transcript_path"], "C:\\t\\events.jsonl")

    def test_transcript_survives_next_prompt(self):
        session_state.upsert_from_payload(
            _payload(transcriptPath="C:\\t\\events.jsonl"), "agentStop"
        )
        session_state.upsert_from_payload(_payload(prompt="again"), "userPromptSubmitted")
        row = self._rows()["abc-123"]
        self.assertEqual(row["status"], "working")
        self.assertEqual(row["transcript_path"], "C:\\t\\events.jsonl")

    def test_session_start_never_downgrades_working(self):
        # Non-interactive Copilot fires sessionStart AFTER userPromptSubmitted
        # (verified live, CLI 1.0.70) — the late arrival must not flip the row.
        session_state.upsert_from_payload(_payload(prompt="go"), "userPromptSubmitted")
        session_state.upsert_from_payload(_payload(source="new"), "sessionStart")
        self.assertEqual(self._rows()["abc-123"]["status"], "working")

    def test_session_start_creates_idle_row_when_absent(self):
        session_state.upsert_from_payload(_payload(source="new"), "sessionStart")
        self.assertEqual(self._rows()["abc-123"]["status"], "idle")

    def test_session_end_deletes_row(self):
        session_state.upsert_from_payload(_payload(prompt="go"), "userPromptSubmitted")
        session_state.remove_from_payload(_payload(reason="complete"))
        self.assertEqual(self._rows(), {})

    def test_unknown_event_is_ignored(self):
        session_state.upsert_from_payload(_payload(), "preToolUse")
        self.assertFalse(session_state.state_file().exists())

    # ---- launcher env join -------------------------------------------------

    def test_launcher_env_identity_is_persisted(self):
        os.environ["APP_LAUNCHER_SESSION_ID"] = "launcher-42"
        os.environ["APP_LAUNCHER_AGENT"] = "Copilot"
        session_state.upsert_from_payload(_payload(prompt="go"), "userPromptSubmitted")
        row = self._rows()["abc-123"]
        self.assertEqual(row["launcher_session_id"], "launcher-42")
        self.assertEqual(row["agent"], "copilot")

    # ---- prune ---------------------------------------------------------------

    def test_stale_rows_pruned_on_write(self):
        old = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat(
            timespec="seconds"
        ).replace("+00:00", "Z")
        session_state.state_file().parent.mkdir(parents=True, exist_ok=True)
        session_state.state_file().write_text(
            json.dumps({"stale-1": {"status": "needs-you", "updated_at": old}}),
            encoding="utf-8",
        )
        session_state.upsert_from_payload(_payload(prompt="go"), "userPromptSubmitted")
        rows = self._rows()
        self.assertIn("abc-123", rows)
        self.assertNotIn("stale-1", rows)

    # ---- corrupt file self-heals --------------------------------------------

    def test_corrupt_state_file_self_heals(self):
        session_state.state_file().parent.mkdir(parents=True, exist_ok=True)
        session_state.state_file().write_text("{not json", encoding="utf-8")
        session_state.upsert_from_payload(_payload(prompt="go"), "userPromptSubmitted")
        self.assertEqual(self._rows()["abc-123"]["status"], "working")


class HookCommandUtf8Tests(unittest.TestCase):
    """The rendered hook command delivers non-ASCII stdin intact (fleet-config-lite#24).

    Drives the template's own ``powershell`` command end to end, under every
    PowerShell Copilot's ``powershell`` key may run in (pwsh 7.6.6 on CLI
    1.0.83, per fleet-config#913; 5.1 covered too). The old
    ``[Console]::In.ReadToEnd() | python`` pipe turned an em dash into ``???``
    (5.1) or cp850 mojibake (pwsh) before ``session_state.py`` saw it.
    """

    REPO = Path(__file__).resolve().parents[1]

    @staticmethod
    def _shells():
        shells = []
        system_root = os.environ.get("SystemRoot")
        if system_root:
            ps51 = Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
            if ps51.exists():
                shells.append(("powershell 5.1", str(ps51)))
        pwsh = shutil.which("pwsh")
        if pwsh:
            shells.append(("pwsh", pwsh))
        return shells

    def test_non_ascii_payload_reaches_hook_intact(self):
        shells = self._shells()
        if not shells:
            self.skipTest("no PowerShell on this host")
        template = json.loads(
            (self.REPO / "hook-config" / "session-state.template.json").read_text(encoding="utf-8")
        )
        command = (
            template["hooks"]["userPromptSubmitted"][0]["powershell"]
            .replace("{{PYTHON}}", Path(sys.executable).as_posix())
            .replace("{{REPO}}", self.REPO.as_posix())
        )
        cwd = "C:\\work\\café—中"
        # Raw UTF-8 codepoints, as Copilot sends them: a default json.dumps
        # would \u-escape them and the check would pass on any transport.
        stdin = json.dumps(
            {"sessionId": "utf8-24", "timestamp": 1, "cwd": cwd, "prompt": "a — b"},
            ensure_ascii=False,
        ).encode("utf-8")
        for name, shell in shells:
            with self.subTest(shell=name), tempfile.TemporaryDirectory() as state_dir:
                env = dict(os.environ, COPILOT_HOOKS_STATE_DIR=state_dir)
                res = subprocess.run(
                    [shell, "-NoProfile", "-NonInteractive", "-Command", command],
                    input=stdin, capture_output=True, timeout=60, env=env,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
                self.assertEqual(res.returncode, 0, res.stderr.decode("utf-8", "replace"))
                rows = json.loads((Path(state_dir) / "sessions-state.json").read_text(encoding="utf-8"))
                self.assertEqual(rows["utf8-24"]["cwd"], cwd)
                self.assertEqual(rows["utf8-24"]["project"], "café—中")


if __name__ == "__main__":
    unittest.main()
