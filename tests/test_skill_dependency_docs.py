"""A skill that imports `skills/_lib/` must not be documented as standalone.

Run:  python -m unittest discover -s tests -v

Routing writes through `skills/_lib/runtime_files.py` gave some skill folders a
sibling dependency; a copy of such a folder alone fails at import. Its own
instructions have to say so, and must not claim the folder works by itself.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / "skills"
LIB_IMPORT = re.compile(r'sys\.path\.insert\(.*"_lib"')
STANDALONE_CLAIMS = (
    "fully self-contained",
    "no dependency on any other repo or checkout;",
    "ships in this folder (`assets/` + `scripts/`); it has no dependency",
)


def skills_importing_lib() -> list[Path]:
    found = set()
    for py in SKILLS.rglob("*.py"):
        if "_lib" in py.relative_to(SKILLS).parts[:1]:
            continue
        if LIB_IMPORT.search(py.read_text(encoding="utf-8")):
            found.add(SKILLS / py.relative_to(SKILLS).parts[0])
    return sorted(found)


class SkillDependencyDocsTests(unittest.TestCase):
    def test_detects_the_known_dependents(self):
        names = {p.name for p in skills_importing_lib()}
        self.assertTrue({"e2e", "learning-log", "slides"} <= names, names)

    def test_dependents_name_the_lib_folder(self):
        for skill in skills_importing_lib():
            text = (skill / "SKILL.md").read_text(encoding="utf-8")
            self.assertTrue("skills/_lib" in text, f"{skill.name}/SKILL.md omits skills/_lib")

    def test_dependents_make_no_standalone_claim(self):
        docs = [REPO / "README.md", REPO / "docs" / "ratchets.md"]
        docs += [s / "SKILL.md" for s in skills_importing_lib()]
        docs += [py for s in skills_importing_lib() for py in s.glob("*.py")]
        for doc in docs:
            text = doc.read_text(encoding="utf-8")
            for claim in STANDALONE_CLAIMS:
                self.assertFalse(claim in text, f"{doc.name} claims: {claim}")


if __name__ == "__main__":
    unittest.main()
