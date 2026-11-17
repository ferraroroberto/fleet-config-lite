"""Tests for hooks/chief_guard.py: the chief's handover, turn-end holds and ask_user deny.

Run:  python -m unittest discover -s tests -v

`chief_ops.py` is replaced by a fake keyed on its verb, so each hold is driven
by the exact line the real verb prints; one case runs the real entry point as
the template's command would.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "hooks"))

import chief_guard  # noqa: E402

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
CHIEF_CWD = "E:/automation/fleet-config-lite"


class GuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.state = Path(self._td.name)
        env = mock.patch.dict(os.environ, {"COPILOT_HOOKS_STATE_DIR": str(self.state)})
        env.start()
        self.addCleanup(env.stop)
        self.lines = {"chief-sid": "CHIEF_SID=chief-1\n", "compact-due": "COMPACT_NOT_DUE percent=10 threshold=30\n",
                      "slots-idle": "SLOTS_IDLE=0 free=3 queued=0\n", "wake": "WAKE=waiter doorbell=off\n"}
        self.calls: list = []
        fake = mock.patch.object(chief_guard, "chief_ops", side_effect=self._fake_ops)
        fake.start()
        self.addCleanup(fake.stop)

    def _fake_ops(self, *args: str):
        self.calls.append(args[0])
        return self.lines.get(args[0])

    def chief_payload(self, **extra) -> dict:
        return {"session_id": "cop-1", "cwd": CHIEF_CWD, **extra}

    def test_only_a_fleet_config_lite_session_pays_for_the_chief_read(self) -> None:
        self.assertFalse(chief_guard.is_chief({"cwd": "E:/automation/other-repo"}, "chief-1"))
        self.assertFalse(chief_guard.is_chief({"cwd": CHIEF_CWD}, ""))
        self.assertEqual(self.calls, [])
        self.assertTrue(chief_guard.is_chief({"cwd": CHIEF_CWD + "-wt-3"}, "chief-1"))
        self.assertFalse(chief_guard.is_chief({"cwd": CHIEF_CWD}, "lane-9"))
        self.lines["chief-sid"] = None
        self.assertFalse(chief_guard.is_chief({"cwd": CHIEF_CWD}, "chief-1"))

    def test_session_start_hands_back_the_handover_log(self) -> None:
        missing = chief_guard.on_session_start(self.chief_payload(), "chief-1")
        self.assertIn("No handover log yet", missing["additionalContext"])
        (self.state / "chief-handover.md").write_text("Batch: lite port, step 7.", encoding="utf-8")
        out = chief_guard.on_session_start(self.chief_payload(), "chief-1")
        self.assertTrue(out["additionalContext"].endswith("Batch: lite port, step 7."))
        self.assertEqual(out["hookSpecificOutput"]["additionalContext"], out["additionalContext"])
        self.assertIsNone(chief_guard.on_session_start(self.chief_payload(), "lane-9"))

    def test_agent_stop_holds_once_for_a_due_compaction(self) -> None:
        self.lines["compact-due"] = "COMPACT_DUE percent=82 threshold=30\n"
        first = chief_guard.on_agent_stop(self.chief_payload(), "chief-1")
        self.assertEqual(first["decision"], "block")
        self.assertIn("self-compact", first["reason"])
        self.assertIsNone(chief_guard.on_agent_stop(self.chief_payload(), "chief-1"))
        self.assertIsNone(chief_guard.on_agent_stop(self.chief_payload(stop_hook_active=True), "chief-1"))

    def test_unknown_compact_state_never_holds(self) -> None:
        self.lines["compact-due"] = "COMPACT_DUE=unknown reason=no session.usage_record\n"
        self.assertIsNone(chief_guard.on_agent_stop(self.chief_payload(), "chief-1"))

    def test_idle_slots_hold_unless_covered(self) -> None:
        self.lines["slots-idle"] = "SLOTS_IDLE=2 free=2 queued=4\nSLOTS_COVERED=slots-idle\n"
        self.assertIsNone(chief_guard.on_agent_stop(self.chief_payload(), "chief-1"))
        self.lines["slots-idle"] = "SLOTS_IDLE=2 free=2 queued=4\n"
        out = chief_guard.on_agent_stop(self.chief_payload(), "chief-1")
        self.assertIn("SLOTS_IDLE=2", out["reason"])

    def test_working_lanes_with_the_doorbell_off_hold_once(self) -> None:
        (self.state / "chief-managed.json").write_text(json.dumps({"lane-1": {"repo": "demo", "number": 1}}),
                                                       encoding="utf-8")
        (self.state / "sessions-state.json").write_text(json.dumps(
            {"c": {"status": "working", "launcher_session_id": "lane-1"}}), encoding="utf-8")
        self.lines["wake"] = "WAKE=doorbell doorbell=on fallback=waiter seconds=3000\n"
        self.assertIsNone(chief_guard.on_agent_stop(self.chief_payload(), "chief-1"))
        self.lines["wake"] = "WAKE=waiter doorbell=off\n"
        out = chief_guard.on_agent_stop(self.chief_payload(), "chief-1")
        self.assertIn("1 lane(s) are working", out["reason"])
        self.assertIsNone(chief_guard.on_agent_stop(self.chief_payload(), "chief-1"))

    def test_ask_user_denied_for_the_chief_and_managed_lanes_only(self) -> None:
        ask = {"tool_name": "ask_user", "cwd": "E:/automation/demo"}
        self.assertIsNone(chief_guard.on_pre_tool_use({"tool_name": "powershell", "cwd": CHIEF_CWD}, "chief-1"))
        self.assertIsNone(chief_guard.on_pre_tool_use(ask, "lane-1"))
        (self.state / "chief-managed.json").write_text(json.dumps({"lane-1": {}}), encoding="utf-8")
        self.assertEqual(chief_guard.on_pre_tool_use(ask, "lane-1")["permissionDecision"], "deny")
        chief = chief_guard.on_pre_tool_use({**ask, "cwd": CHIEF_CWD}, "chief-1")
        self.assertEqual(chief["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIsNone(chief_guard.on_pre_tool_use(ask, ""))


class EntryPointTests(unittest.TestCase):
    def test_pre_tool_use_entry_point_denies_ask_user_for_a_managed_lane(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "chief-managed.json").write_text(json.dumps({"lane-1": {}}), encoding="utf-8")
            env = {**os.environ, "COPILOT_HOOKS_STATE_DIR": td, "APP_LAUNCHER_SESSION_ID": "lane-1", "PYTHONUTF8": "1"}
            proc = subprocess.run([sys.executable, str(REPO / "hooks" / "chief_guard.py"), "preToolUse"],
                                  input=json.dumps({"toolName": "ask_user", "cwd": td}), capture_output=True,
                                  text=True, timeout=30, env=env, creationflags=NO_WINDOW)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout)["permissionDecision"], "deny")

    def test_template_registers_the_three_events_on_this_module(self) -> None:
        hooks = json.loads((REPO / "hooks" / "chief-guard.template.json").read_text(encoding="utf-8"))["hooks"]
        self.assertEqual(set(hooks), {"sessionStart", "agentStop", "preToolUse"})
        for event, entries in hooks.items():
            self.assertTrue(entries[0]["powershell"].endswith(f"/hooks/chief_guard.py' {event}"))


if __name__ == "__main__":
    unittest.main()
