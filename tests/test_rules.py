"""Rules around the editing: AI error sorting, posting times, Instagram captions, invites, the server's .env tool."""
from tests import _env  # noqa: F401  (first: throwaway folders)

import os
import subprocess
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from instagram.publish import MAX_CAPTION, MAX_TAGS, caption_for
from pipeline.ai import gemini_error_kind, openai_error_kind
from web import invites
from youtube.schedule_times import plan_times

ROOT = Path(__file__).resolve().parent.parent


class Err(Exception):
    def __init__(self, msg="", code=None, status_code=None):
        super().__init__(msg)
        self.code, self.status_code = code, status_code


class AiErrors(unittest.TestCase):
    def test_gemini(self):
        cases = {"busy": [Err(code=503), Err("The model is overloaded"), Err("Deadline exceeded")],
                 "limit": [Err(code=429), Err("RESOURCE_EXHAUSTED: quota")],
                 "missing": [Err(code=404), Err("models/gemini-1.0 is not found")],
                 "bad_key": [Err(code=403), Err("API key not valid")],
                 "other": [Err("something odd")]}
        for kind, errs in cases.items():
            for e in errs:
                self.assertEqual(gemini_error_kind(e), kind, str(e))

    def test_openai(self):
        self.assertEqual(openai_error_kind(Err("insufficient_quota", status_code=429)), "no_credit")
        self.assertEqual(openai_error_kind(Err(status_code=429)), "limit")
        self.assertEqual(openai_error_kind(Err(status_code=502)), "busy")
        self.assertEqual(openai_error_kind(Err("model_not_found", status_code=404)), "missing")


class PostingTimes(unittest.TestCase):
    def test_now(self):
        self.assertEqual(plan_times(3, "now"), [None, None, None])

    def test_presets_start_tomorrow_at_fixed_hours(self):
        tz = "America/Chicago"
        for mode, hours in (("d12", {12}), ("d18", {18}), ("two", {12, 18})):
            got = plan_times(4, mode, tz)
            self.assertEqual(len(got), 4)
            self.assertEqual({t.hour for t in got}, hours)
            self.assertTrue(all(t > datetime.now(t.tzinfo) for t in got))
            self.assertEqual(got, sorted(got))

    def test_custom_spacing(self):
        start = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
        got = plan_times(3, "custom", "Asia/Kolkata", start, every_hours=12)
        self.assertEqual([(b - a).total_seconds() for a, b in zip(got, got[1:])], [43200, 43200])
        self.assertEqual(plan_times(2, "custom", None, start, every_hours=5)[1] - plan_times(2, "custom", None, start)[0],
                         timedelta(hours=24))  # not offered: 24 h

    def test_custom_too_soon_or_missing(self):
        soon = (datetime.now() + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M")
        for start in (soon, "", "tomorrow"):
            with self.assertRaises(RuntimeError):
                plan_times(1, "custom", None, start)

    def test_dst_change_keeps_the_hour(self):
        got = plan_times(30, "d18", "America/New_York")
        self.assertEqual({t.hour for t in got}, {18})


class InstagramCaption(unittest.TestCase):
    def test_limits(self):
        it = {"ig_caption": "x" * 5000 + " #one #two", "hashtags": [f"tag{k}" for k in range(40)]}
        got = caption_for(it, {})
        self.assertLessEqual(len(got), MAX_CAPTION)
        self.assertLessEqual(len(set(t.lower() for t in __import__("re").findall(r"#(\w+)", got))), MAX_TAGS)

    def test_typed_hashtags_not_repeated(self):
        got = caption_for({"ig_caption": "Best day #Travel", "hashtags": ["travel", "food"]}, {})
        self.assertEqual(got.lower().count("#travel"), 1)
        self.assertIn("#reels", got)


class Invites(unittest.TestCase):
    def setUp(self):
        self.path = Path(os.environ["INVITES_FILE"])
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("# beta\nMaya@Example.com   # from the meetup\nraj@example.com\n", encoding="utf-8")

    def tearDown(self):
        os.environ["INVITE_ONLY"] = ""

    def test_open_when_off(self):
        os.environ["INVITE_ONLY"] = ""
        self.assertTrue(invites.invited("anyone@example.com"))

    def test_only_listed_emails_when_on(self):
        os.environ["INVITE_ONLY"] = "1"
        self.assertTrue(invites.invited(" maya@example.com "))
        self.assertTrue(invites.invited("RAJ@example.com"))
        self.assertFalse(invites.invited("ma.ya@example.com"))
        self.assertFalse(invites.invited("example.com"))
        self.assertFalse(invites.invited(""))

    def test_missing_file_lets_nobody_in(self):
        os.environ["INVITE_ONLY"] = "1"
        self.path.unlink()
        self.assertFalse(invites.invited("maya@example.com"))


class EnvTool(unittest.TestCase):
    def run_tool(self, f, *args):
        subprocess.run([sys.executable, str(ROOT / "deploy" / "envtool.py"), str(f), *args], check=True,
                       capture_output=True, text=True)
        return f.read_text(encoding="utf-8")

    def test_never_overwrites_unless_forced(self):
        f = Path(_env.TMP) / "test.env"
        f.write_text("# keys\nGEMINI_API_KEY=abc\nJOB_SLOTS=2\nEMPTY=\n", encoding="utf-8")
        text = self.run_tool(f, "GEMINI_API_KEY=zzz", "EMPTY=filled", "NEW=1")
        self.assertIn("GEMINI_API_KEY=abc", text)
        self.assertIn("EMPTY=filled", text)
        self.assertTrue(text.rstrip().endswith("NEW=1"))
        self.assertTrue(text.startswith("# keys"))
        text = self.run_tool(f, "--force", "JOB_SLOTS=1")
        self.assertIn("JOB_SLOTS=1", text)
        self.assertIn("GEMINI_API_KEY=abc", text)
        out = subprocess.run([sys.executable, str(ROOT / "deploy" / "envtool.py"), str(f), "--empty", "EMPTY",
                              "OTHER"], capture_output=True, text=True).stdout.split()
        self.assertEqual(out, ["OTHER"])


if __name__ == "__main__":
    unittest.main()
