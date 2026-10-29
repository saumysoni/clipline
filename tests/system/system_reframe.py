"""
System test of Reframe (pipeline/smart_reframe.py) with the real FFmpeg: a vlog whose colour says where in the picture a
pixel is (red = across, green = down), so a frame of the Short shows exactly what part of the vlog it framed. Moves on the
vlog's clock land at the right times of a Short made of two pieces; a zoom shows a smaller part; Fit and Split are
1080x1920 with the views asked for; the command file is gone after; the Captions preview frames the same way.

    python -m unittest discover -s tests/system -t . -p "system_*.py"
"""
import os

os.environ["PITCREW_REAL_MEDIA"] = "1"

from tests import fakes as F  # noqa: E402,F401  (clean settings, throwaway folders)

import subprocess  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

from pipeline import probe  # noqa: E402
from pipeline.caption_preview import caption_frame  # noqa: E402
from pipeline.ffmpeg import ffmpeg_exe  # noqa: E402
from pipeline.fonts import prepare_job_fonts  # noqa: E402
from pipeline.render import render_short  # noqa: E402
from tests.system.system_pipeline import frame_at  # noqa: E402


def where(img, x, y):
    """(across, down) of the vlog, 0-1, that pixel (x, y) of a frame shows."""
    r, g, _ = img.getpixel((x, y))
    return r / 255, g / 255


class RealReframe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp())
        cls.src = cls.dir / "source.mp4"
        subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                        "color=black:s=1920x1080:d=12:r=30,geq=r='X/W*255':g='Y/H*255':b=128",
                        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", "12", "-c:v", "libx264", "-preset", "ultrafast",
                        "-crf", "12", "-pix_fmt", "yuv444p", "-c:a", "aac", "-shortest", str(cls.src)], check=True)
        cls.meta = probe(cls.src)
        prepare_job_fonts(cls.dir)

    def make(self, moment, n):
        name, _ = render_short(self.src, self.meta, {"hook_mode": "none", **moment}, [], n, "bold", self.dir, cx=None)
        self.assertEqual(list(self.dir.glob("reframe_*.cmd")), [])  # the command file is gone
        out = self.dir / name
        self.assertEqual((probe(out)["width"], probe(out)["height"]), (1080, 1920))
        return out

    def test_moves_land_on_the_vlogs_clock_across_pieces(self):
        # pieces 1-4 and 6-10 of the vlog: vlog 7 s is 4 s into the Short. Cut: the frame jumps there.
        out = self.make({"start": 1, "end": 10, "pieces": [[1, 4], [6, 10]],
                         "reframe": {"cut": True, "moves": [{"t": 1, "x": 0.2}, {"t": 7, "x": 0.8}]}}, 1)
        self.assertAlmostEqual(where(frame_at(out, 2.0), 540, 960)[0], 0.2, delta=0.04)
        self.assertAlmostEqual(where(frame_at(out, 3.5), 540, 960)[0], 0.2, delta=0.04)  # after the join, before the move
        self.assertAlmostEqual(where(frame_at(out, 4.6), 540, 960)[0], 0.8, delta=0.04)

    def test_a_glide_and_a_zoom(self):
        out = self.make({"start": 1, "end": 7, "reframe": {"moves": [{"t": 1, "x": 0.5}, {"t": 4, "x": 0.5, "y": 0.2, "z": 2.5}]}}, 2)
        wide, close = frame_at(out, 1.0), frame_at(out, 3.5)
        span = lambda img: where(img, 1060, 960)[0] - where(img, 20, 960)[0]
        self.assertAlmostEqual(span(wide), 608 / 1920, delta=0.04)          # the full height: 608 px of the vlog across
        self.assertAlmostEqual(span(close), 608 / 1920 / 2.5, delta=0.03)   # 2.5 times in
        self.assertAlmostEqual(where(close, 540, 960)[1], 0.2, delta=0.04)  # and up
        mid = where(frame_at(out, 3.0 - 0.3), 540, 960)[1]  # the move is at vlog 4 s = 3 s in; it glides there in GLIDE s
        self.assertTrue(0.22 < mid < 0.48, mid)

    def test_a_zoom_on_a_small_vlog(self):
        """640x360 (low-resolution vlogs are common): zooming in and out keeps every frame, 1080x1920."""
        small = self.dir / "small.mp4"
        subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(self.src), "-vf", "scale=640:360", "-c:v", "libx264",
                        "-preset", "ultrafast", "-crf", "12", "-pix_fmt", "yuv444p", "-c:a", "copy", str(small)], check=True)
        meta = probe(small)
        name, _ = render_short(small, meta, {"hook_mode": "none", "start": 1, "end": 7, "reframe": {"cut": True, "moves": [
            {"t": 1, "x": 0.5}, {"t": 3, "x": 0.8, "z": 2}, {"t": 5, "x": 0.2, "z": 1.3}]}}, [], 5, "bold", self.dir, cx=None)
        out = self.dir / name
        n = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                            "stream=nb_read_frames,width,height", "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout.strip()
        self.assertEqual(n.split(",")[:2], ["1080", "1920"])
        self.assertGreaterEqual(int(n.split(",")[2]), 175)  # 6 s at 30 fps: every frame, not one
        span = lambda img: where(img, 1060, 960)[0] - where(img, 20, 960)[0]
        self.assertAlmostEqual(span(frame_at(out, 3.0)), 202.5 / 640 / 2, delta=0.04)

    def test_shots_and_punch_ins(self):
        """Auto layout's shots: Fit (the whole width) in its shots, the frame in the others; punch-ins zoom in and out."""
        out = self.make({"start": 1, "end": 9, "pieces": [[1, 4], [5, 9]], "reframe": {"moves": [{"t": 1, "x": 0.5}],
                         "shots": [{"t": 1, "fit": False}, {"t": 3, "fit": True}, {"t": 6, "fit": False}],
                         "punch": {"amount": 0.25, "at": [7, 8]}}}, 6)
        span = lambda img: where(img, 1060, 960)[0] - where(img, 20, 960)[0]
        fill = 608 / 1920
        self.assertAlmostEqual(span(frame_at(out, 1.0)), fill, delta=0.04)            # vlog 2 s: framed
        self.assertGreater(span(frame_at(out, 2.5)), 0.9)                              # vlog 3.5 s: a Fit shot, all of it
        self.assertGreater(span(frame_at(out, 3.5)), 0.9)                              # vlog 5.5 s (after the cut): still Fit
        self.assertAlmostEqual(span(frame_at(out, 4.5)), fill, delta=0.04)            # vlog 6.5 s: framed again
        self.assertAlmostEqual(span(frame_at(out, 5.5)), fill / 1.25, delta=0.03)     # vlog 7.5 s: punched in
        self.assertAlmostEqual(span(frame_at(out, 6.5)), fill, delta=0.04)            # vlog 8.5 s: back out

    def test_auto_shots_and_tracking(self):
        """On a vlog that cuts from a picture to another (no faces: both Fit), and a square moving across it (tracked)."""
        from pipeline.smart_reframe import auto_shots, track_moves
        clip = self.dir / "cuts.mp4"
        subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error",
                        "-f", "lavfi", "-i", "testsrc2=s=1280x720:d=3:r=30", "-f", "lavfi", "-i", "color=c=0x224488:s=1280x720:d=3:r=30",
                        "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]", "-map", "[v]", "-c:v", "libx264", "-preset", "ultrafast",
                        "-pix_fmt", "yuv420p", str(clip)], check=True)
        r = auto_shots(clip, probe(clip), [(0, 6)])
        self.assertEqual([round(x["t"]) for x in r["shots"]], [0, 3])
        self.assertTrue(all(x["fit"] for x in r["shots"]))
        moving = self.dir / "moving.mp4"
        subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0x303030:s=1280x720:d=4:r=30",
                        "-f", "lavfi", "-i", "color=c=0xffcc00:s=120x120:d=4:r=30",
                        "-filter_complex", "[1:v]drawbox=x=30:y=30:w=60:h=60:color=0x2040ff:t=fill[sq];"
                        "[0:v]noise=alls=8:allf=t[bg];[bg][sq]overlay=x='100+t*200':y=300[v]", "-map", "[v]",
                        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(moving)], check=True)
        moves, until = track_moves(moving, probe(moving), [(0, 4)], 0.0, 160 / 1280, 360 / 720)
        self.assertGreater(until, 3.0)
        last = moves[-1]
        expect = (160 + last["t"] * 200) / 1280
        self.assertAlmostEqual(last["x"], expect, delta=0.05)

    def test_fit_and_split(self):
        fit = frame_at(self.make({"start": 2, "end": 5, "reframe": {"layout": "fit"}}, 3), 1.0)
        left, right = where(fit, 4, 960)[0], where(fit, 1075, 960)[0]
        self.assertTrue(left < 0.05 and right > 0.95, (left, right))  # the whole width
        split = frame_at(self.make({"start": 2, "end": 5, "reframe": {"layout": "split", "top": {"x": 0.4},
                                                                       "bottom": {"x": 0.6}}}, 4), 1.0)
        self.assertAlmostEqual(where(split, 540, 480)[0], 0.4, delta=0.04)
        self.assertAlmostEqual(where(split, 540, 1440)[0], 0.6, delta=0.04)

    def test_preview_frames_the_same(self):
        from PIL import Image
        import io
        m = {"start": 1, "end": 10, "pieces": [[1, 4], [6, 10]], "hook_mode": "none",
             "reframe": {"cut": True, "moves": [{"t": 1, "x": 0.2}, {"t": 7, "x": 0.8}]}}
        jpg = Image.open(io.BytesIO(caption_frame(self.src, self.meta, m, [], 7.6, "bold", self.dir))).convert("RGB")
        self.assertAlmostEqual(where(jpg, jpg.width // 2, jpg.height // 2)[0], 0.8, delta=0.05)
        self.assertEqual(list(self.dir.glob("reframe_*.cmd")), [])


if __name__ == "__main__":
    unittest.main()
