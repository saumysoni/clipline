"""Small rules many features rely on: thumbnail plans and layout, both looks, vlog chapters and tags, times typed by
creators, the links pasted in the setup form, plain error sentences, Short descriptions."""
from tests import _env  # noqa: F401  (first: throwaway folders)

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pipeline.text import fmt_mmss, parse_time
from pipeline.thumbnails import layout, plan
from pipeline.vlog_meta import clean_chapters, clean_tags, compose_description, stamp
from youtube.links import link_kind, video_id_from_url, video_link_problem, youtube_link_problem


def frame(w=1920, h=1080, color=(90, 120, 160)):
    return Image.new("RGB", (w, h), color)


class ThumbnailPlan(unittest.TestCase):
    def test_tidy_lines(self):
        self.assertEqual(plan.tidy_lines("Rice Older?", "Older Than Me"), ("Rice", "Older Than Me"))
        self.assertEqual(plan.tidy_lines("  BIG   day ", "x" * 50), ("BIG day", "x" * 30))
        self.assertEqual(plan.tidy_lines("!!", "Wow"), ("", "Wow"))

    def test_clean_plan_validates_everything(self):
        frames = [frame() for _ in range(4)]
        m = {"title": "T", "thumb_line1": "Hey", "thumb_line2": "There"}
        good = plan.clean_plan({"frame": 2, "focus": [100, 200, 600, 700], "line1": "A", "line2": "B",
                                "accent": plan.ACCENTS[3]}, frames, m)
        self.assertEqual((good["frame"], good["accent"], good["line1"]), (2, plan.ACCENTS[3], "A"))
        bad = plan.clean_plan({"frame": 99, "focus": [5, 5, 6, 6], "accent": "#123456"}, frames, m)
        self.assertTrue(0 <= bad["frame"] < 4)
        self.assertIn(bad["accent"], plan.ACCENTS)
        self.assertEqual(bad["line2"], "There")  # the Short's own text when the AI gave none
        self.assertIsInstance(plan.clean_plan("nonsense", frames, m)["frame"], int)

    def test_each_short_gets_its_own_colour(self):
        d = Path(tempfile.mkdtemp())
        for i, c in enumerate(plan.ACCENTS[:3], 1):
            (d / f"thumbwork_{i}").mkdir()
            (d / f"thumbwork_{i}" / "plan.json").write_text(json.dumps({"accent": c}))
        got = plan.fresh_accent(d, "thumbwork_9", plan.ACCENTS[0])
        self.assertNotIn(got, plan.ACCENTS[:3])
        self.assertEqual(plan.fresh_accent(d, "thumbwork_1", plan.ACCENTS[0]), plan.ACCENTS[0])  # its own

    def test_old_plans_upgraded(self):
        up = plan.upgrade_plan({"face_frame": 3, "face_box": [1, 2, 300, 400], "items": [], "line1": "a a", "line2": "a"})
        self.assertEqual((up["frame"], up["focus"]), (3, [1, 2, 300, 400]))
        self.assertNotIn("items", up)


class ThumbnailLayout(unittest.TestCase):
    def test_portrait_keeps_the_face_in_view(self):
        img = frame()
        out = layout.portrait(img, (100, 850, 400, 990))  # a face at the far right edge
        self.assertEqual(out.size, (layout.W, layout.H))
        out2 = layout.portrait(frame(320, 180), None)  # tiny source: blown up and sharpened, still 1080x1920
        self.assertEqual(out2.size, (layout.W, layout.H))

    def test_text_goes_where_there_is_room(self):
        canvas = Image.new("RGBA", (layout.W, layout.H))
        top, scale = layout.text_spot(canvas, "small", "HEADLINE", (0.6, 0.8))
        self.assertTrue(top)
        self.assertEqual(scale, 1.0)
        top, _ = layout.text_spot(canvas, "small", "HEADLINE", (0.05, 0.35))
        self.assertFalse(top)
        _, scale = layout.text_spot(canvas, "a long small line", "A VERY LONG HEADLINE HERE", (0.2, 0.85))
        self.assertGreaterEqual(scale, 0.5)

    def test_both_looks_draw_under_2mb(self):
        frames = [frame(color=(30 * i, 80, 140)) for i in range(4)]
        for look in layout.LOOKS:
            pl = {"frame": 1, "focus": [200, 300, 700, 700], "line1": "WE GOT", "line2": "LOST", "accent": "#FFD60A",
                  "look": look}
            img = layout.compose(frames, pl)
            self.assertEqual(img.size, (layout.W, layout.H), look)
            path = Path(tempfile.mkdtemp()) / "t.jpg"
            layout.save(img.convert("RGB"), path)
            self.assertLess(path.stat().st_size, 2 * 1024 * 1024, look)
        self.assertEqual(layout.compose(frames, {"frame": 0, "look": "collage", "line2": "x"}).size, (layout.W, layout.H))


class VlogDetails(unittest.TestCase):
    def test_chapters_follow_youtubes_rules(self):
        got = clean_chapters([{"t": 5, "title": "Intro"}, {"t": 8, "title": "too close"}, {"t": 60, "title": "Road"},
                              {"t": 120, "title": "Market"}, {"t": 595, "title": "past the end"}], 600)
        self.assertEqual([c["t"] for c in got], [0, 60, 120])
        self.assertEqual(clean_chapters([{"t": 0, "title": "a"}, {"t": 60, "title": "b"}], 600), [])  # fewer than 3
        self.assertEqual(stamp(3729), "1:02:09")
        self.assertEqual(stamp(65), "1:05")
        d = compose_description("Hi.", got, ["travel", "#road trip"])
        self.assertIn("0:00 Intro\n1:00 Road", d)
        self.assertTrue(d.endswith("#travel #roadtrip"))

    def test_tags(self):
        tags = clean_tags(["Hills", "hills", "#Road, Trip", "", "x" * 100] + [f"tag{i}" for i in range(200)])
        self.assertEqual(tags[:2], ["hills", "road trip"])
        self.assertLessEqual(sum(len(t) + 2 for t in tags), 500)


class Times(unittest.TestCase):
    def test_parse_time(self):
        for text, want in (("2:10", 130), ("1:02:10", 3730), ("130", 130), ("130.5", 130.5), (" 0:05 ", 5)):
            self.assertEqual(parse_time(text), want, text)
        for bad in ("", "abc", "1:2:3:4", "-5", "1:999"):
            self.assertIsNone(parse_time(bad), bad)
        self.assertEqual(fmt_mmss(65.9), "1:05")

    def test_read_times(self):
        from web.times import read_times
        self.assertEqual(read_times("0:10", "0:40"), (10, 40))
        self.assertIsNone(read_times("", ""))
        for a, b in (("0:40", "0:10"), ("x", "0:10"), ("0:10", "")):
            with self.assertRaises(RuntimeError):
                read_times(a, b)


class Links(unittest.TestCase):
    def test_kinds_and_problems(self):
        self.assertEqual(video_id_from_url("https://youtu.be/dQw4w9WgXcQ?t=3"), "dQw4w9WgXcQ")
        self.assertEqual(video_id_from_url("https://www.youtube.com/shorts/dQw4w9WgXcQ"), "dQw4w9WgXcQ")
        self.assertEqual(link_kind("https://drive.google.com/file/d/abc/view"), "drive_file")
        self.assertEqual(link_kind("drive.google.com/drive/folders/abc"), "drive_folder")
        self.assertEqual(link_kind("https://www.youtube.com/@channel"), "youtube_page")
        self.assertIsNone(video_link_problem("https://drive.google.com/file/d/abc/view"))
        self.assertIn("can't download videos from YouTube", video_link_problem("https://youtu.be/dQw4w9WgXcQ"))
        self.assertIsNone(youtube_link_problem("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
        self.assertIn("Google Drive", youtube_link_problem("https://drive.google.com/file/d/abc/view"))


class PlainErrors(unittest.TestCase):
    def test_raw_errors_become_sentences(self):
        from web.errors import plain_error
        for raw in ("Command failed: ffmpeg -y ... Conversion failed!", "Traceback (most recent call last): KeyError",
                    "503 UNAVAILABLE", "429 RESOURCE_EXHAUSTED"):
            msg = plain_error(raw, "Editing Shorts")
            self.assertTrue(msg and msg[0].isupper() and msg.rstrip().endswith((".", "!")), (raw, msg))
            self.assertNotIn("Traceback", msg)
            self.assertNotIn("ffmpeg -y", msg)
        ok = "Couldn't download that link. Make sure sharing is set to 'Anyone with the link'."
        self.assertEqual(plain_error(ok, ""), ok)  # plain sentences pass through


class ShortDescription(unittest.TestCase):
    def test_links_and_mentions(self):
        from web.posting import short_description, youtube_title
        d = short_description({"hook": "Wait for it", "hashtags": ["travel"]},
                              {"youtube_url": "https://youtu.be/dQw4w9WgXcQ", "channel_handle": "@hills"})
        self.assertEqual(d.split("\n\n"), ["Wait for it", "Watch the full video: https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                                           "More from @hills", "#travel #Shorts"])
        d = short_description({"hook": "x", "hook_mode": "none", "title": "Title", "hashtags": []}, {}, {"title": "Chan"})
        self.assertTrue(d.startswith("Title"))
        self.assertIn("More from Chan", d)
        self.assertEqual(youtube_title("Hi"), "Hi #Shorts")
        self.assertEqual(youtube_title("Hi #shorts"), "Hi #shorts")
        self.assertEqual(youtube_title("x" * 95), "x" * 95)


if __name__ == "__main__":
    unittest.main()
