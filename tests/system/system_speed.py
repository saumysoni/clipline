"""
System test of the quick ways Pit Crew reads a vlog, with the real FFmpeg (they count most on a small server):
the face finder reads only the keyframes when a phone put enough of them (pipeline/reframe.py), the long way otherwise;
Auto layout's search for new shots stops at the end of the Short's part instead of reading on to the end of the vlog
(pipeline/smart_reframe.py scene_changes); Reframe's smart buttons read a small copy of the Short's part, made when
Reframe opens, with the same answers, and the copy goes with the vlog's video (web/reframe_look.py); the Captions
preview keeps the framed picture, so a change at the same moment only draws the captions (pipeline/caption_preview.py).

    python -m unittest discover -s tests/system -t . -p "system_*.py"
"""
import os

os.environ["PITCREW_REAL_MEDIA"] = "1"

from tests import fakes as F  # noqa: E402,F401  (clean settings, throwaway folders)

import subprocess  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

from pipeline import reframe, smart_reframe  # noqa: E402
from pipeline.ffmpeg import ffmpeg_exe  # noqa: E402


def make(path, seconds, gop, picture="testsrc2=size=1280x720:rate=30"):
    subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", picture, "-t", str(seconds),
                    "-c:v", "libx264", "-preset", "ultrafast", "-g", str(gop), "-pix_fmt", "yuv420p", str(path)],
                   check=True, stdin=subprocess.DEVNULL)
    return path


class QuickReading(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp())
        cls.phone = make(cls.dir / "phone.mp4", 20, 30)  # a keyframe every second, like a phone
        cls.sparse = make(cls.dir / "sparse.mp4", 20, 300)  # one keyframe for the whole video

    def test_keyframes_only_when_a_phone_put_enough(self):
        pics = reframe.key_frames(self.phone, 4, 14, 640)
        self.assertTrue(9 <= len(pics) <= 11, len(pics))
        self.assertTrue(all(p.shape == (360, 640) and p.dtype.name == "uint8" for p in pics))
        self.assertGreater(float(pics[0].std()), 10)  # a real picture, not an empty one
        looks = reframe._looks(self.phone, 4, 14, 1280)
        self.assertEqual(len(looks), len(pics))
        self.assertTrue(all(w == 1280 for _, w in looks))
        # few keyframes: read through, a picture a second
        self.assertLessEqual(len(reframe.key_frames(self.sparse, 4, 14, 640)), 1)
        looks = reframe._looks(self.sparse, 4, 14, 1280)
        self.assertTrue(9 <= len(looks) <= 11, len(looks))
        self.assertTrue(all(p.shape == (360, 640) and w == 1280 for p, w in looks))
        # the face finder still runs either way (no face in a test picture: None, never an error)
        self.assertIsNone(reframe.face_center_x(self.phone, 4, 14, 1280))
        self.assertIsNone(reframe.face_center_x(self.sparse, 4, 14, 1280))

    def test_keyframes_are_quicker_than_reading_the_clip(self):
        t = time.time()
        reframe._looks(self.phone, 2, 18, 1280)
        quick = time.time() - t
        t = time.time()
        reframe._every_second(self.phone, 2, 18)
        slow = time.time() - t
        self.assertLess(quick, slow)

    def test_new_shots_are_looked_for_only_inside_the_part(self):
        # red until 3 s, blue until 40 s, green after: the part 1-6 s has one new shot, at 3 s
        long = self.dir / "cuts.mp4"
        subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error",
                        "-f", "lavfi", "-i", "color=red:s=640x360:r=30:d=3", "-f", "lavfi", "-i", "color=blue:s=640x360:r=30:d=37",
                        "-f", "lavfi", "-i", "color=green:s=640x360:r=30:d=20",
                        "-filter_complex", "[0][1][2]concat=n=3:v=1:a=0", "-c:v", "libx264", "-preset", "ultrafast",
                        "-pix_fmt", "yuv420p", str(long)], check=True, stdin=subprocess.DEVNULL)
        cuts = smart_reframe.scene_changes(long, 1, 6)
        self.assertEqual(len(cuts), 1, cuts)  # not the one at 40 s: the reading stopped at 6 s
        self.assertAlmostEqual(cuts[0], 3, delta=0.1)


class ReframeCopy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from settings import JOBS_DIR
        F.install()
        F.reset()
        cls.c = F.client(F.new_user())
        # a vlog with a patterned square moving across it (what Tap to track follows)
        src = make(Path(tempfile.mkdtemp()) / "vlog.mp4", 90, 30,
                   "color=c=0x305070:s=1280x720:r=30[bg];testsrc2=s=160x160:r=30[fg];[bg][fg]overlay=x='200+4*t':y=280")
        with_sound = src.with_name("vlog_sound.mp4")
        subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(src), "-f", "lavfi", "-i",
                        "sine=frequency=330:sample_rate=48000", "-shortest", "-c:v", "copy", "-c:a", "aac", str(with_sound)],
                       check=True, stdin=subprocess.DEVNULL)
        up = F.upload(cls.c, with_sound)
        jid = cls.c.post("/api/start", data={"upload": up, "count": "1", "style": "bold"}).get_json()["id"]
        st = F.wait_ready(cls.c, jid, timeout=600)
        assert st["status"] == "ready", st
        cls.jid, cls.s, cls.dir = jid, st["shorts"][0], JOBS_DIR / jid

    def test_2_buttons_read_the_copy_with_the_same_answers_and_it_goes_with_the_video(self):
        from pipeline import probe, smart_reframe
        from web import reframe_look, retention
        idx, s = self.s["idx"], self.s
        at = s["start"] + 2
        x = (200 + 4 * at + 80) / 1280
        direct = smart_reframe.track_moves(self.dir / "source.mp4", probe(self.dir / "source.mp4"), [(s["start"], s["end"])],
                                           at, x, 360 / 720)
        num = reframe_look.number(s)
        look, info = reframe_look.paths(self.jid, num)
        self.assertTrue(look.is_file() and info.is_file())  # made with the Short
        have = reframe_look.covered(self.jid, num)
        self.assertAlmostEqual(have[0], s["start"], delta=0.02)
        self.assertAlmostEqual(have[1], s["end"], delta=0.02)
        r = self.c.post(f"/api/reframe/{self.jid}/{idx}/track", json={"at": at, "x": x, "y": 0.5})
        meta = probe(look)
        self.assertEqual((meta["width"], meta["height"]), (reframe_look.LOOK_WIDTH, 360))
        self.assertAlmostEqual(meta["duration"], s["end"] - s["start"], delta=0.2)
        got = r.get_json()
        self.assertGreaterEqual(len(got["moves"]), 2, got)
        self.assertAlmostEqual(got["moves"][0]["x"], x, delta=0.02)
        self.assertAlmostEqual(got["until"], direct[1], delta=0.5)
        t, worst = at, {"copy": 0, "vlog": 0}
        while t < got["until"] - 1:  # as close to where the square really is as reading the vlog itself
            truth = (200 + 4 * t + 80) / 1280
            worst["copy"] = max(worst["copy"], abs(smart_reframe.framing_at(got["moves"], t)[0] - truth))
            worst["vlog"] = max(worst["vlog"], abs(smart_reframe.framing_at(direct[0], t)[0] - truth))
            t += 0.25
        self.assertLess(worst["copy"], max(0.08, worst["vlog"] + 0.02), worst)
        src = reframe_look.source(self.jid, s, {"path": self.dir / "source.mp4", "offset": 0.0, "reach": (0, 90), "clip": False},
                                  [(s["start"], s["end"])])
        self.assertEqual(src["path"], look)
        far = reframe_look.source(self.jid, s, {"path": self.dir / "source.mp4", "offset": 0.0, "reach": (0, 90), "clip": False},
                                  [(0.0, 89.0)])  # further than the copy: the vlog itself
        self.assertEqual(far["path"], self.dir / "source.mp4")
        self.assertIn(look, retention._short_files(self.dir, s))  # deleted with the Short
        self.assertEqual(self.c.post(f"/api/reframe/{self.jid}/{idx}/auto", json={}).status_code, 200)
        # a Short made before copies were: opening Reframe makes one (in the background)
        look.unlink()
        info.unlink()
        self.assertEqual(self.c.get(f"/api/reframe/{self.jid}/{idx}").status_code, 200)
        F.wait(lambda: info.is_file(), timeout=120, what="the copy made when Reframe opened")
        self.assertTrue(look.is_file())
        self.assertEqual(probe(look)["width"], reframe_look.LOOK_WIDTH)
        from web.vlogs import remove_video
        remove_video(self.jid)
        self.assertEqual(list(self.dir.glob("look_*")), [])  # and with the vlog's video

    def test_1_captions_preview_keeps_the_picture(self):
        import io
        from PIL import Image, ImageChops
        from pipeline import caption_preview as CP
        idx = self.s["idx"]
        url = f"/api/captions/{self.jid}/{idx}/preview"
        if not (self.dir / "source.mp4").exists():
            self.skipTest("the video was removed first (test_2 removes it: run in name order)")
        CP._BASES.clear()
        at = self.s["start"] + 3
        first = self.c.post(url, json={"at": at})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(len(CP._BASES), 1)
        again = self.c.post(url, json={"at": at})
        a, b = (Image.open(io.BytesIO(x.data)).convert("RGB") for x in (first, again))
        self.assertEqual(a.size, b.size)
        diff = ImageChops.difference(a, b).convert("L").histogram()
        self.assertLess(sum(i * n for i, n in enumerate(diff)) / sum(diff), 2)  # the same picture (JPEG noise only)
        self.assertEqual(len(CP._BASES), 1)
        self.c.post(url, json={"at": at + 1})  # another moment: another picture
        self.assertEqual(len(CP._BASES), 2)
        moving = {"layout": "fill", "moves": [{"t": self.s["start"], "x": 0.2}, {"t": self.s["start"] + 5, "x": 0.8}]}
        self.assertEqual(self.c.post(url, json={"at": at, "reframe": moving}).status_code, 200)
        self.assertEqual(len(CP._BASES), 2)  # a moving frame isn't kept
        self.assertEqual(list(self.dir.glob("capprev_*")), [])


if __name__ == "__main__":
    unittest.main()
