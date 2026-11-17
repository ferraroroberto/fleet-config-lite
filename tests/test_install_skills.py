"""install.ps1 must never write skills through a junctioned skills dir (stdlib unittest).

Run:  python -m unittest discover -s tests -v

On a full-fleet machine `~/.copilot/skills` is a junction into another repo's
skills/, so a link created in it lands inside that repo. Each case copies the
installer, its hook templates and one fake skill into a temp "repo" and points
COPILOT_HOME at a temp folder, so nothing outside the temp tree is touched.
Windows only: the installer is PowerShell and the hazard is an NTFS junction.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
POWERSHELL = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _ps(command: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                          capture_output=True, text=True, timeout=120, env=env, creationflags=NO_WINDOW)


def _remove_links(root: Path) -> None:
    """Delete every junction under `root` as a link, before the temp tree is removed."""
    for dirpath, dirnames, _files in os.walk(root):
        for name in list(dirnames):
            path = Path(dirpath) / name
            if path.is_junction() or path.is_symlink():
                os.rmdir(path)
                dirnames.remove(name)


@unittest.skipUnless(sys.platform == "win32" and Path(POWERSHELL).exists(), "Windows PowerShell installer")
class InstallSkillsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        self.addCleanup(self._td.cleanup)
        self.addCleanup(_remove_links, self.root)
        self.repo = self.root / "lite"
        (self.repo / "hooks").mkdir(parents=True)
        shutil.copy2(REPO / "install.ps1", self.repo / "install.ps1")
        for template in (REPO / "hooks").glob("*.template.json"):
            shutil.copy2(template, self.repo / "hooks" / template.name)
        shutil.copy2(REPO / "global-instructions.md", self.repo / "global-instructions.md")
        (self.repo / "skills" / "demo").mkdir(parents=True)
        (self.repo / "skills" / "demo" / "SKILL.md").write_text("demo", encoding="utf-8")
        self.home = self.root / "copilot-home"
        self.home.mkdir()

    def install(self) -> subprocess.CompletedProcess:
        env = {**os.environ, "COPILOT_HOME": str(self.home)}
        return subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                               str(self.repo / "install.ps1")], capture_output=True, text=True, timeout=180,
                              env=env, creationflags=NO_WINDOW)

    def test_a_junctioned_skills_dir_is_never_written_through(self) -> None:
        other = self.root / "full-fleet" / "skills"
        other.mkdir(parents=True)
        made = _ps(f"New-Item -ItemType Junction -Path '{self.home / 'skills'}' -Target '{other}' | Out-Null")
        self.assertEqual(made.returncode, 0, made.stderr)
        proc = self.install()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("[skip] skills dir is a link into another tree", proc.stdout)
        self.assertEqual(list(other.iterdir()), [])

    def test_a_real_skills_dir_gets_links_and_a_rerun_keeps_the_source(self) -> None:
        for _ in range(2):
            proc = self.install()
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        link = self.home / "skills" / "demo"
        self.assertTrue(link.is_junction())
        self.assertEqual((self.repo / "skills" / "demo" / "SKILL.md").read_text(encoding="utf-8"), "demo")


if __name__ == "__main__":
    unittest.main()
