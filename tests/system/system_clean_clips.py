"""
System test of clean clips (pipeline/clean_clip.py) with the real FFmpeg: a vlog whose colour changes every second (so a
frame says when it's from), a clean clip of a moment, then the same Short rendered from the vlog and from the clip (at its
offset): the same frames, a moving frame included, and the Captions preview too. A 4K-ish vlog's clip is 1080 on its short
side.

    python -m unittest discover -s tests/system -t . -p "system_*.py"
"""
import os

os.environ["PITCREW_REAL_MEDIA"] = "1"

from tests import fakes as F  # noqa: E402,F401

import io  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

from PIL import Image  # noqa: E402

from pipeline import probe  # noqa: E402
from pipeline.caption_preview import caption_frame  # noqa: E402
from pipeline.clean_clip import clip_reach, make_clean_clip  # noqa: E402
from pipeline.ffmpeg import ffmpeg_exe  # noqa: E402
from pipeline.fonts import prepare_job_fonts  # noqa: E402
from pipeline.render import render_short  # noqa: E402
from tests.system.system_pipeline import frame_at  # noqa: E402


def px(img, x, y):
    return img.convert("RGB").getpixel((x, y))


def close(a, b, tol=12):
    return all(abs(p - q) <= tol for p, q in zip(a, b))


class RealCleanClips(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp())
        cls.src = cls.dir / "source.mp4"
        # red: which second (x 9), green: across the picture, blue: half a second on / off
        subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                        "color=black:s=1280x720:d=60:r=30,geq=r='mod(floor(T)*9\\,256)':g='X/W*255':b='if(lt(mod(T\\,1)\\,0.5)\\,40\\,200)'",
                        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", "60", "-c:v", "libx264", "-preset", "ultrafast",
                        "-crf", "10", "-pix_fmt", "yuv444p", "-g", "15", "-c:a", "aac", "-shortest", str(cls.src)], check=True)
        cls.meta = probe(cls.src)
        prepare_job_fonts(cls.dir)

    def test_same_short_from_the_vlog_and_from_its_clip(self):
        moment = {"start": 21, "end": 33, "pieces": [[21, 25], [28, 33]], "hook_mode": "none",
                  "reframe": {"cut": True, "moves": [{"t": 21, "x": 0.3}, {"t": 29, "x": 0.7}]}}
        a, b = clip_reach([(21, 25), (28, 33)], 60)
        self.assertEqual((a, b), (0.0, 60.0))
        a, b = clip_reach([(21, 25), (28, 33)], 60, pad=10)
        clip = self.dir / "clip_1.mp4"
        info = make_clean_clip(self.src, self.meta, a, b, clip)
        self.assertEqual((info["from"], info["scale"]), (11.0, 1.0))
        self.assertAlmostEqual(probe(clip)["duration"], b - a, delta=0.1)
        v1, _ = render_short(self.src, self.meta, moment, [], 1, "bold", self.dir, cx=None)
        v2, _ = render_short(clip, probe(clip), moment, [], 2, "bold", self.dir, cx=None, offset=info["from"])
        for t in (0.6, 3.4, 4.6, 6.2, 8.4):  # both pieces, either side of the join and of the move (vlog 29 s = 5 s in)
            f1, f2 = frame_at(self.dir / v1, t), frame_at(self.dir / v2, t)
            for x, y in ((540, 960), (100, 300), (1000, 1600)):
                self.assertTrue(close(px(f1, x, y), px(f2, x, y)), (t, x, y, px(f1, x, y), px(f2, x, y)))
        # and the preview frame, at a vlog time
        j1 = Image.open(io.BytesIO(caption_frame(self.src, self.meta, moment, [], 30.2, "bold", self.dir)))
        j2 = Image.open(io.BytesIO(caption_frame(clip, probe(clip), moment, [], 30.2, "bold", self.dir, offset=info["from"])))
        self.assertTrue(close(px(j1, 270, 480), px(j2, 270, 480)))

    def test_a_big_vlog_clip_is_1080(self):
        big = self.dir / "big.mp4"
        subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(self.src), "-t", "6", "-vf", "scale=2560:1440",
                        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "copy", str(big)], check=True)
        info = make_clean_clip(big, probe(big), 1, 5, self.dir / "clip_2.mp4")
        m = probe(self.dir / "clip_2.mp4")
        self.assertEqual((m["width"], m["height"], info["scale"]), (1920, 1080, 0.75))


if __name__ == "__main__":
    unittest.main()
