"""
System test of Captions (web/captions.py, pipeline/captions.py, pipeline/caption_preview.py) with the real FFmpeg and
libass: a Short remade in a bundled font, higher up, in other colours; libass really uses the bundled font file (not a
stand-in); the highlight colour shows where the captions were moved to; the preview frame shows the same.

    python -m unittest discover -s tests/system -t . -p "system_*.py"
"""
import os

os.environ["PITCREW_REAL_MEDIA"] = "1"  # before tests.fakes: the real pipeline, not the quick stand-ins

from tests import fakes as F  # noqa: E402

import io  # noqa: E402
import subprocess  # noqa: E402
import unittest  # noqa: E402

from PIL import Image  # noqa: E402

from pipeline import captions as C  # noqa: E402
from settings import JOBS_DIR  # noqa: E402
from tests.system.system_pipeline import frame_at  # noqa: E402

GREEN = "#00FF00"


def green(img, top, bottom):
    """Pixels close to pure green between rows top and bottom."""
    px, (w, _) = img.load(), img.size
    return sum(1 for x in range(0, w, 2) for y in range(top, bottom, 2)
               if (lambda p: p[1] > 180 and p[0] < 110 and p[2] < 110)(px[x, y]))


class RealCaptions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        F.install()
        F.reset()
        cls.c = F.client(F.new_user())
        up = F.upload(cls.c, F.test_video(90, "640x360", plain=True))
        jid = cls.c.post("/api/start", data={"upload": up, "count": "1", "style": "bold"}).get_json()["id"]
        st = F.wait_ready(cls.c, jid, timeout=600)
        assert st["status"] == "ready", st
        cls.jid, cls.s, cls.dir = jid, st["shorts"][0], JOBS_DIR / jid
        cls.base = f"/api/captions/{jid}/{cls.s['idx']}"
        # Bebas Neue, green highlight, near the middle, one word a line (so the spoken word is the whole line)
        cls.caps = {**C.preset("cinema"), "hi": GREEN, "color": GREEN, "bottom": 1000, "words": 1, "anim": "none"}

    def short(self):
        return F.wait(lambda: (x := next(y for y in F.job_json(self.jid)["shorts"] if y["idx"] == self.s["idx"]))
                      and not x.get("retrying") and x, timeout=300, what="remade")

    def test_remade_in_the_bundled_font_and_place(self):
        r = self.c.post(self.base, json={"captions": self.caps, "remake": True})
        self.assertEqual(r.status_code, 200, r.get_json())
        me = self.short()
        self.assertFalse(me.get("retry_error"), me.get("retry_error"))
        video = self.dir / me["video"]
        ass = video.with_name(me["video"].replace("short_", "captions_").replace(".mp4", ".ass"))
        self.assertIn("Style: Cap,Bebas Neue,", ass.read_text())
        # libass picks the bundled file itself, not a look-alike (gotchas 4 and 25)
        from pipeline.ffmpeg import ffmpeg_exe
        log = subprocess.run([ffmpeg_exe(), "-v", "verbose", "-f", "lavfi", "-i", "color=c=black:s=1080x1920:d=8:r=4",
                              "-vf", f"subtitles={ass.name}:fontsdir=fonts", "-f", "null", "-"],
                             cwd=self.dir, capture_output=True, text=True).stderr
        picked = [ln for ln in log.splitlines() if "fontselect" in ln and "Bebas" in ln]
        self.assertTrue(picked and "(Bebas Neue, 400, 0) -> BebasNeue-Regular" in picked[0], "\n".join(picked) or log[-800:])
        # the words are green, around 1000 px from the bottom, and not where captions usually are (560)
        hits = [green(frame_at(video, t), 1920 - 1000 - 220, 1920 - 1000 + 20) for t in (3.0, 6.0, 9.0)]
        low = [green(frame_at(video, t), 1920 - 560 - 160, 1920 - 560 + 20) for t in (3.0, 6.0, 9.0)]
        self.assertGreater(max(hits), 50, hits)
        self.assertEqual(max(low), 0, low)

    def test_preview_frame(self):
        r = self.c.post(self.base + "/preview", json={"captions": self.caps, "at": self.s["start"] + 6})
        self.assertEqual((r.status_code, r.mimetype), (200, "image/jpeg"), r.get_data()[:200])
        img = Image.open(io.BytesIO(r.data)).convert("RGB")
        self.assertEqual(img.size, (540, 960))
        self.assertGreater(green(img, (1920 - 1000 - 220) // 2, (1920 - 1000 + 20) // 2), 15)
        off = self.c.post(self.base + "/preview", json={"captions": {**self.caps, "on": False}, "at": self.s["start"] + 6})
        self.assertEqual(green(Image.open(io.BytesIO(off.data)).convert("RGB"), 0, 960), 0)
        self.assertEqual(list(self.dir.glob("capprev_*")), [])  # nothing left behind

    def test_motion_preview(self):
        """A few seconds of silent video, so lines coming in (pop, fade) can be seen before saving."""
        from tests.system.system_pipeline import probe
        r = self.c.post(self.base + "/preview", json={"captions": {**self.caps, "anim": "pop"}, "at": self.s["start"] + 6,
                                                       "motion": True})
        self.assertEqual((r.status_code, r.mimetype), (200, "video/mp4"), r.get_data()[:200])
        clip = self.dir / "motion_check.mp4"
        clip.write_bytes(r.data)
        m = probe(clip)
        self.assertEqual((m["width"], m["height"], m["codec"]), (540, 960, "h264"))
        self.assertAlmostEqual(m["duration"], 2.5, delta=0.2)
        self.assertGreater(green(frame_at(clip, 1.0), (1920 - 1000 - 220) // 2, (1920 - 1000 + 20) // 2), 15)
        self.assertEqual(list(self.dir.glob("capprev_*")), [])


if __name__ == "__main__":
    unittest.main()
