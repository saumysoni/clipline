"""The page's own files: every script parses (a syntax error in one stops the whole page), every file index.html lists
exists, and every section it includes is there. Needs Node.js for the syntax check (skipped where it isn't installed)."""
from tests import _env  # noqa: F401  (first: clean settings)

import re
import shutil
import subprocess
import unittest
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "static"


class PageFiles(unittest.TestCase):
    def test_every_listed_file_exists(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        files = re.findall(r'(?:src|href)="/static/([^"?#]+)"', html)
        self.assertGreater(len(files), 30)
        for f in files:
            self.assertTrue((STATIC / f).is_file(), f"index.html lists {f}, which doesn't exist")
        for name in re.findall(r"<!--\s*include\s+([\w./-]+)\s*-->", html):
            self.assertTrue((STATIC / "sections" / Path(name).name).is_file() or (STATIC / name).is_file(), name)

    @unittest.skipUnless(shutil.which("node"), "Node.js isn't installed here")
    def test_every_script_parses(self):
        bad = []
        for js in sorted((STATIC / "js").glob("*.js")) + sorted((STATIC / "legal").glob("*.js")):  # + the homepage's
            r = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
            if r.returncode:
                lines = r.stderr.strip().splitlines()
                why = next((ln for ln in lines if "Error" in ln), lines[0] if lines else "?")
                where = next((ln for ln in lines if js.name in ln), "")
                bad.append(f"{js.name}: {why} {where.split(js.name)[-1]}")
        self.assertEqual(bad, [])

    def test_ids_the_scripts_need_are_on_the_page(self):
        """Every $("id") a script uses exists in index.html or a section (or is made by a script)."""
        markup = (STATIC / "index.html").read_text(encoding="utf-8") + "".join(
            p.read_text(encoding="utf-8") for p in (STATIC / "sections").glob("*.html"))
        scripts = "".join(p.read_text(encoding="utf-8") for p in (STATIC / "js").glob("*.js"))
        ids = set(re.findall(r'\$\("([A-Za-z][\w-]*)"\)', scripts))
        made = set(re.findall(r'\.id\s*=\s*"([\w-]+)"', scripts)) | set(re.findall(r"""id=["']([\w-]+)["']""", scripts))
        missing = sorted(i for i in ids if f'id="{i}"' not in markup and i not in made)
        self.assertEqual(missing, [], "scripts look up ids that no page has")

    def test_homepage_parts(self):
        """The homepage's script finds what it animates, and its own files load only there."""
        home = (STATIC / "legal" / "welcome.html").read_text(encoding="utf-8")
        script = (STATIC / "legal" / "home.js").read_text(encoding="utf-8")
        for i in set(re.findall(r'\$\("([A-Za-z][\w-]*)"\)', script)):
            self.assertIn(f'id="{i}"', home)
        for tab in re.findall(r'aria-controls="(\w+)"', home):
            self.assertIn(f'id="{tab}"', home)
        self.assertTrue((STATIC / "legal" / "home.css").is_file())


if __name__ == "__main__":
    unittest.main()
