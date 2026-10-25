"""The verification run's structure-ratchet stage (stdlib unittest, no deps).

Run:  python -m unittest discover -s tests -v

`scripts/structure_ratchet.py` exits 3 when it could not measure the tree (git
unusable, an unparseable file, an unknown `shape`): nothing was checked. Only
exit 0 passes here, so 3 fails as NOT CONFIRMED -- never a pass, never a skip.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "structure_ratchet.py"

# One `ast` parse per Python file plus a `git ls-files`; the bound only turns a
# hung child into NOT CONFIRMED.
RUN_TIMEOUT_S = 180

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def run_ratchet(script: Path = SCRIPT) -> tuple[int, str]:
    """`(exit_code, output)`; a script that hangs or cannot start reads as exit 3."""
    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8",
            errors="replace", stdin=subprocess.DEVNULL, creationflags=_NO_WINDOW,
            timeout=RUN_TIMEOUT_S, check=False,
        )
    except subprocess.TimeoutExpired:
        return 3, f"{script.name} did not finish in {RUN_TIMEOUT_S}s"
    except OSError as exc:
        return 3, f"{script.name} could not start: {exc}"
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def passed(code: int) -> bool:
    """Only exit 0 passes: 1 and 2 are findings or bad config, 3 is NOT CONFIRMED."""
    return code == 0


def assert_ratchet_passes(case: unittest.TestCase, script: Path) -> None:
    """Run one vendored ratchet and fail `case` unless it exits 0; exit 3 reads as NOT CONFIRMED."""
    code, output = run_ratchet(script)
    case.assertTrue(passed(code), f"exit {code}" + (" (NOT CONFIRMED)" if code == 3 else "") + f"\n{output}")


class ExitMapping(unittest.TestCase):
    def test_only_exit_zero_passes_and_three_is_not_a_pass(self) -> None:
        self.assertTrue(passed(0))
        for code in (1, 2, 3, 4, -1):
            self.assertFalse(passed(code), code)

    def _fake(self, tmp: Path, code: int) -> Path:
        script = tmp / "fake_ratchet.py"
        script.write_text(f"import sys\nprint('from the script')\nsys.exit({code})\n", encoding="utf-8")
        return script

    def test_every_non_zero_exit_fails_and_exit_three_is_not_a_pass(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            for code in (0, 1, 2, 3):
                got, output = run_ratchet(self._fake(Path(d), code))
                self.assertEqual(got, code)
                self.assertIn("from the script", output)


class Declaration(unittest.TestCase):
    def test_ratchet_is_declared_and_its_script_is_vendored(self) -> None:
        fleet = tomllib.loads((REPO_ROOT / ".fleet.toml").read_text(encoding="utf-8"))
        self.assertIs(fleet["structure_ratchet"]["enabled"], True)
        self.assertTrue((REPO_ROOT / fleet["structure_ratchet"]["baseline"]).is_file())
        self.assertEqual(fleet["shape"], "skills-governance")
        entry = fleet["vendored"]["structure_ratchet"]
        self.assertEqual(entry["dest"], "scripts/structure_ratchet.py")
        self.assertTrue((REPO_ROOT / entry["dest"]).is_file())


class RealRepoRatchet(unittest.TestCase):
    def test_no_new_or_grown_offender_and_the_layout_matches(self) -> None:
        code, output = run_ratchet()
        self.assertEqual(code, 0, f"exit {code}" + (" (NOT CONFIRMED)" if code == 3 else "") + f"\n{output}")


if __name__ == "__main__":
    unittest.main()
