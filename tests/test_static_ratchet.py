"""The verification run's static-ratchet stage (stdlib unittest, no deps).

Run:  python -m unittest discover -s tests -v

`scripts/static_ratchet.py` exits 3 when a detector could not run (no `npx`, no
ruff, a timeout): nothing was checked. The mapping tests pin that 3 fails as
NOT CONFIRMED -- never a pass, never a skip -- using fake scripts in a temp
directory. `RealRepoRatchet` then runs the vendored script on this repo for
real, so a new unused import or duplicate block turns the unit run red by key.
That case needs ruff and Node (`npx`; the first run downloads jscpd); without
them it fails as NOT CONFIRMED rather than skipping.
"""

from __future__ import annotations

import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import static_ratchet_gate as gate  # noqa: E402


def _fake_script(tmp: Path, code: int, message: str = "") -> Path:
    script = tmp / "fake_ratchet.py"
    script.write_text(f"import sys\nprint({message!r})\nsys.exit({code})\n", encoding="utf-8")
    return script


class ExitMapping(unittest.TestCase):
    def test_only_exit_zero_passes(self) -> None:
        self.assertTrue(gate.classify_exit(0)[0])
        for code in (1, 2, 3, 4, -1):
            self.assertFalse(gate.classify_exit(code)[0], code)

    def test_exit_three_is_not_confirmed_and_never_a_skip(self) -> None:
        ok, label = gate.classify_exit(3)
        self.assertFalse(ok)
        self.assertIn("NOT CONFIRMED", label)
        self.assertNotIn("skip", label.lower())

    def test_run_fails_for_every_script_failure(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            for code, expected in ((0, 0), (1, 1), (2, 1), (3, 1)):
                got, report = gate.run(_fake_script(Path(d), code, "from the script"))
                self.assertEqual(got, expected, code)
                self.assertIn("from the script", report)  # the script's own finding is echoed
                self.assertTrue(report.splitlines()[-1].startswith("OK" if code == 0 else "FAIL"))

    def test_run_reports_a_detector_that_could_not_run(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            got, report = gate.run(_fake_script(Path(d), 3, "npx was not found"))
        self.assertEqual(got, 1)
        self.assertIn("npx was not found", report)
        self.assertIn("NOT CONFIRMED", report)

    def test_timeout_and_unstartable_script_are_not_confirmed(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            script = _fake_script(Path(d), 0)
            for exc in (gate.subprocess.TimeoutExpired(cmd="x", timeout=1), OSError("no interpreter")):
                with mock.patch.object(gate.subprocess, "run", side_effect=exc):
                    got, report = gate.run(script)
                self.assertEqual(got, 1)
                self.assertIn("NOT CONFIRMED", report)

    def test_wrapper_runs_under_the_current_interpreter(self) -> None:
        real = gate.subprocess.run
        with tempfile.TemporaryDirectory() as d, mock.patch.object(
            gate.subprocess, "run", side_effect=real
        ) as spy:
            gate.run(_fake_script(Path(d), 0))
        self.assertEqual(spy.call_args.args[0][0], sys.executable)  # the python that has ruff


class Declaration(unittest.TestCase):
    def test_ratchet_is_declared_and_its_script_is_vendored(self) -> None:
        fleet = tomllib.loads((REPO_ROOT / ".fleet.toml").read_text(encoding="utf-8"))
        self.assertIs(fleet["static_ratchet"]["enabled"], True)
        self.assertTrue((REPO_ROOT / fleet["static_ratchet"]["baseline"]).is_file())
        entry = fleet["vendored"]["static_ratchet"]
        self.assertEqual(entry["dest"], "scripts/static_ratchet.py")
        self.assertTrue((REPO_ROOT / entry["dest"]).is_file())


class RealRepoRatchet(unittest.TestCase):
    def test_no_new_duplicate_block_or_unused_import(self) -> None:
        code, report = gate.run()
        self.assertEqual(code, 0, report)


if __name__ == "__main__":
    unittest.main()
