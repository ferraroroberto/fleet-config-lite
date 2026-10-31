"""Pins the cleanup-fleet ship override against the skills it delegates to.

`/issue-yolo` and `/issue-finish` always write `Closes #<N>`; a partial
cleanup of an audit issue must not auto-close it, so `/cleanup-fleet` has to
carry an explicit `Part of #<N>` override plus the post-merge ticking step.
The override is prose, so this test fails when either side drifts.
"""

from __future__ import annotations

import unittest
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[1] / "skills"


def _text(name: str) -> str:
    return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


class CleanupFleetShipOverrideTests(unittest.TestCase):
    def test_delegated_skills_still_default_to_closes(self) -> None:
        for name in ("issue-yolo", "issue-finish"):
            self.assertIn("Closes #<N>", _text(name), name)

    def test_cleanup_fleet_overrides_the_closing_keyword(self) -> None:
        text = _text("cleanup-fleet")
        self.assertIn("Part of #<N>", text)
        self.assertIn("audit_gate.py upsert", text)

    def test_cleanup_fleet_does_not_claim_the_mr_ticks_boxes(self) -> None:
        self.assertNotIn("The MR ticks the boxes", _text("cleanup-fleet"))


if __name__ == "__main__":
    unittest.main()
