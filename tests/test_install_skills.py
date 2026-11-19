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
        self.profile = self.root / "profile"
        self.home = self.profile / ".copilot"
        self.home.mkdir(parents=True)

    def install(self, checklist: bool = False) -> subprocess.CompletedProcess:
        env = {**os.environ, "COPILOT_HOME": str(self.home), "USERPROFILE": str(self.profile)}
        flags = ["-SkipVenv"] if checklist else ["-SkipVenv", "-SkipChecklist"]
        return subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                               str(self.repo / "install.ps1"), *flags],
                              capture_output=True, text=True, timeout=180, env=env, creationflags=NO_WINDOW)

    def junction(self, link: Path, target: Path) -> None:
        target.mkdir(parents=True, exist_ok=True)
        link.parent.mkdir(parents=True, exist_ok=True)
        made = _ps(f"New-Item -ItemType Junction -Path '{link}' -Target '{target}' | Out-Null")
        self.assertEqual(made.returncode, 0, made.stderr)

    def hook(self, name: str) -> str:
        return (self.home / "hooks" / f"fleet-config-lite-{name}.json").read_text(encoding="utf-8")

    def test_a_junctioned_skills_dir_is_never_written_through(self) -> None:
        other = self.root / "full-fleet" / "skills"
        self.junction(self.home / "skills", other)
        proc = self.install()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("[skip] skills not installed on a shared machine", proc.stdout)
        self.assertEqual(list(other.iterdir()), [])

    def test_a_real_skills_dir_gets_links_and_a_rerun_keeps_the_source(self) -> None:
        for _ in range(2):
            proc = self.install()
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        link = self.home / "skills" / "demo"
        self.assertTrue(link.is_junction())
        self.assertEqual((self.repo / "skills" / "demo" / "SKILL.md").read_text(encoding="utf-8"), "demo")


    def test_the_checklist_names_git_access_to_gitlab_as_unknown_when_no_remote_exists(self) -> None:
        # The temp tree has no git checkout, so nothing can be asked: the line must say so,
        # not read [ok] on glab's sign-in alone.
        shutil.copytree(REPO / "skills" / "_lib", self.repo / "skills" / "_lib")
        proc = self.install(checklist=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("[unknown] git access to GitLab not confirmed: no https GitLab remote found", proc.stdout)

    def test_a_dedicated_machine_records_every_session_and_links_everything(self) -> None:
        proc = self.install()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("--lite-sessions-only", self.hook("session-state"))
        self.assertNotIn("{{SCOPE}}", self.hook("session-state"))
        self.assertTrue((self.home / "copilot-instructions.md").exists())

    def test_a_shared_machine_changes_nothing_for_other_sessions(self) -> None:
        other = self.root / "full-fleet" / "skills"
        self.junction(self.profile / ".agents" / "skills", other)
        proc = self.install()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("[note] shared machine", proc.stdout)
        self.assertIn("--lite-sessions-only", self.hook("session-state"))
        self.assertIn("chief_guard.py", self.hook("chief-guard"))
        self.assertIn("[skip] instructions not linked on a shared machine", proc.stdout)
        self.assertIn("[skip] skills not installed on a shared machine", proc.stdout)
        self.assertFalse((self.home / "copilot-instructions.md").exists())
        self.assertFalse((self.home / "skills" / "demo").exists())
        self.assertEqual(list(other.iterdir()), [])

    def test_a_linked_hooks_folder_is_never_written_through(self) -> None:
        other = self.root / "elsewhere" / "hooks"
        self.junction(self.home / "hooks", other)
        proc = self.install()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("[skip] hooks folder is a link into another tree", proc.stdout)
        self.assertEqual(list(other.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
