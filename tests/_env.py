"""
Imported first by every test: the same clean settings on a laptop and on the server, and nothing real touched.

  - .env is never read (load_dotenv is switched off before Pit Crew is imported), and every setting .env.example lists
    is removed from the environment, so the server's keys, AI provider, limits and storage times can't change a
    result or reach a real service. Pit Crew's own defaults apply, plus the few test values below.
  - The database, jobs folder and invite list live in a throwaway folder; the background timers are off.
So a test can never touch real accounts, vlogs or the internet (CLAUDE.md, gotcha 16), even run as root on the
live server.
"""
import atexit
import os
import re
import shutil
import tempfile
from pathlib import Path

import dotenv

dotenv.load_dotenv = lambda *a, **k: False  # app.py / serve.py: never the real .env

# A restarted test server (tests/system) carries on with the same throwaway folders.
_KEEP = os.environ.get("PITCREW_KEEP_DIRS") == "1" and os.environ.get("JOBS_DIR") and os.environ.get("DATABASE_PATH")
_KEPT = (os.environ.get("JOBS_DIR"), os.environ.get("DATABASE_PATH")) if _KEEP else None

_EXAMPLE = Path(__file__).resolve().parent.parent / ".env.example"
for _name in re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", _EXAMPLE.read_text(encoding="utf-8"), flags=re.M):
    os.environ.pop(_name, None)
for _name in ("GEMINI_MODEL", "OPENAI_MODEL", "AI_PROVIDER", "THUMB_AI_PROVIDER", "HF_HOME", "FFMPEG_PATH"):
    os.environ.pop(_name, None)

TMP = Path(_KEPT[0]).parent if _KEPT else Path(tempfile.mkdtemp(prefix="pitcrew-test-"))
os.environ.update({
    "DATABASE_PATH": _KEPT[1] if _KEPT else str(TMP / "data" / "test.db"),
    "JOBS_DIR": _KEPT[0] if _KEPT else str(TMP / "jobs"),
    "RETENTION_OFF": "1",
    "INVITES_FILE": str(TMP / "data" / "invites.txt"),
    "COVER_FRAME": "0",
    "SUPPORT_EMAIL": "help@pitcrew.test",
    "X264_PRESET": "ultrafast",
})
(TMP / "jobs").mkdir(parents=True, exist_ok=True)

if not _KEPT and os.environ.get("PITCREW_KEEP_TEST_FILES") != "1":  # (keep them to look at: PITCREW_KEEP_TEST_FILES=1)
    atexit.register(shutil.rmtree, TMP, True)
