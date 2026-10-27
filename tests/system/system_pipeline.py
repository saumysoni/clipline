"""
System tests of the real editing pipeline (FFmpeg, libass captions, face finder, designed thumbnails, cover frame,
preview copy, vlog thumbnail), driven through the app like a creator would. Only the AI and the speech model are
fakes (tests/fakes.py), so it needs no keys and no model download, and runs the same on a laptop and the server.

    python -m unittest discover -s tests/system -t . -p "system_*.py"
"""
import os

os.environ["PITCREW_REAL_MEDIA"] = "1"  # before tests.fakes: the real pipeline, not the quick stand-ins

from tests import fakes as F  # noqa: E402

import json  # noqa: E402
import subprocess  # noqa: E402
import unittest  # noqa: E402

from PIL import Image  # noqa: E402

from settings import JOBS_DIR  # noqa: E402


def probe(path):
    from pipeline.ffmpeg import probe as p
    return p(path)


def frame_at(path, t):
    from pipeline.ffmpeg import ffmpeg_exe
    out = path.with_name(f"frame_{t:.2f}.png")
    subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1",
                    str(out)], check=True)
    return Image.open(out).convert("RGB")


def yellow_pixels(img, box):
    """Pixels close to the word highlight (#FFD60A) inside box (left, top, right, bottom)."""
    n = 0
    px = img.crop(box).load()
    w, h = box[2] - box[0], box[3] - box[1]
    for x in range(0, w, 2):
        for y in range(0, h, 2):
            r, g, b = px[x, y]
            n += r > 200 and 170 < g < 235 and b < 90
    return n


class RealPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        F.install()
        F.reset()
        cls.u = F.new_user()
        cls.c = F.client(cls.u)
        cls.video = F.test_video(120, "640x360", plain=True)  # plain picture: any yellow is the caption highlight
        cls.jid, cls.st = cls._make()
        cls.dir = JOBS_DIR / cls.jid

    @classmethod
    def _make(cls):
        up = F.upload(cls.c, cls.video)
        r = cls.c.post("/api/start", data={"upload": up, "count": "2", "style": "bold"})
        jid = r.get_json()["id"]
        st = F.wait_ready(cls.c, jid, timeout=600)
        assert st["status"] == "ready", st
        return jid, st

    def test_shorts_are_vertical_with_sound_and_the_right_length(self):
        for s in self.st["shorts"]:
            m = probe(self.dir / s["video"])
            self.assertEqual((m["width"], m["height"]), (1080, 1920))
            self.assertAlmostEqual(m["duration"], s["end"] - s["start"], delta=0.35)
            self.assertTrue(m.get("has_audio", True))
            self.assertEqual(m.get("codec"), "h264")

    def test_captions_are_burned_in_with_the_highlight(self):
        s = self.st["shorts"][0]
        ass = (self.dir / f"captions_{s['idx']}.ass").read_text(encoding="utf-8")
        first = next(ln for ln in ass.splitlines() if ln.startswith("Dialogue: 0,"))
        h, mi, sec = first.split(",")[1].split(":")
        t = int(h) * 3600 + int(mi) * 60 + float(sec) + 0.05
        img = frame_at(self.dir / s["video"], t)
        lower = (0, 1000, 1080, 1920)  # captions sit in the lower part (MarginV 560)
        self.assertGreater(yellow_pixels(img, lower), 50, "no highlighted caption word on the frame")
        self.assertEqual(yellow_pixels(frame_at(self.dir / s["video"], 0.01), (0, 0, 1080, 300)), 0)  # none elsewhere

    def test_hook_banner_on_the_first_seconds(self):
        s = self.st["shorts"][0]
        img = frame_at(self.dir / s["video"], 0.5)
        top = img.crop((0, 150, 1080, 450)).convert("L")
        self.assertGreater(sum(1 for p in top.getdata() if p > 235), 5000, "no white hook banner at the top")

    def test_designed_thumbnail(self):
        s = self.st["shorts"][0]
        img = Image.open(self.dir / s["thumb"])
        self.assertEqual(img.size, (1080, 1920))
        self.assertLess((self.dir / s["thumb"]).stat().st_size, 2 * 1024 * 1024)
        work = self.dir / (s.get("thumb_work") or f"thumbwork_{s['thumb'].split('_')[1].split('.')[0]}")
        self.assertTrue((work / "plan.json").exists(), "not the designed thumbnail")
        self.assertEqual(json.loads((work / "plan.json").read_text())["line2"], "BIG DAY")

    def test_switch_look_redraws_without_ai(self):
        before = len(F.AI.calls)
        self.c.post(f"/api/look/{self.jid}/2", json={"look": "duotone"})
        s = F.wait(lambda: (x := next(y for y in F.job_json(self.jid)["shorts"] if y["idx"] == 2)) and
                   not x.get("retrying") and x, timeout=60, what="look")
        self.assertFalse(s.get("retry_error"), s.get("retry_error"))
        self.assertEqual(s["thumb_look"], "duotone")
        self.assertTrue((self.dir / s["thumb"]).exists())
        self.assertEqual(len(F.AI.calls), before)

    def test_new_hook_renders_again(self):
        self.c.post(f"/api/hook/{self.jid}/1", json={"text": "This is the hook"})
        s = F.wait(lambda: (x := next(y for y in F.job_json(self.jid)["shorts"] if y["idx"] == 1)) and
                   not x.get("retrying") and x, timeout=120, what="hook")
        self.assertFalse(s.get("retry_error"), s.get("retry_error"))
        self.assertTrue((self.dir / s["video"]).exists())
        self.assertEqual(probe(self.dir / s["video"])["height"], 1920)

    def test_ai_edit_joins_the_kept_pieces(self):
        s = F.job_json(self.jid)["shorts"][1]
        a, b = s["start"], s["end"]
        keep = [[a, a + 6], [a + 10, a + 16], [a + 20, b]]
        r = self.c.post(f"/api/ai-edit/{self.jid}/{s['idx']}/apply", json={"pieces": keep})
        self.assertEqual(r.status_code, 200, r.get_json())
        me = F.wait(lambda: (x := next(y for y in F.job_json(self.jid)["shorts"] if y["idx"] == s["idx"])) and
                    not x.get("retrying") and x, timeout=120, what="cut")
        self.assertFalse(me.get("retry_error"), me.get("retry_error"))
        m = probe(self.dir / me["video"])
        self.assertEqual((m["width"], m["height"]), (1080, 1920))
        self.assertAlmostEqual(m["duration"], sum(y - x for x, y in keep), delta=0.35)
        from pipeline.cover import audio_format
        self.assertIsNotNone(audio_format(self.dir / me["video"]))  # the sound is joined too

    def test_cover_frame_for_upload(self):
        import pipeline
        s = self.st["shorts"][1]
        out = pipeline.covered_video(self.dir, s["video"], s["thumb"])
        m, orig = probe(out), probe(self.dir / s["video"])
        self.assertAlmostEqual(m["duration"], orig["duration"] + 0.2, delta=0.12)
        self.assertEqual((m["width"], m["height"]), (1080, 1920))

    def test_preview_copy(self):
        import pipeline
        out = self.dir / "preview_test.mp4"
        pipeline.make_preview(next(self.dir.glob("source.*")), out)
        m = probe(out)
        self.assertLessEqual(m["height"], 480)
        self.assertAlmostEqual(m["duration"], 120, delta=1)

    def test_vlog_thumbnail_and_poster(self):
        import pipeline
        name = pipeline.make_vlog_thumbnail(self.video, 120, self.dir, "A day in the hills", "WE GOT", "LOST")
        self.assertEqual(Image.open(self.dir / name).size, (1280, 720))
        again = pipeline.redraw_vlog_thumbnail(self.dir, look="duotone")
        self.assertTrue((self.dir / again).exists())
        pipeline.make_poster(self.video, self.dir / "poster_test.jpg", 120)
        self.assertTrue((self.dir / "poster_test.jpg").exists())


if __name__ == "__main__":
    unittest.main()
