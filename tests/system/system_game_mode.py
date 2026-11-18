"""
System test of Game Mode's framing (pipeline/game_frame.py) with the real FFmpeg render: a "stream" whose colour says
where in the picture a pixel is (red = across, green = down), as in system_reframe.py. A montage of three far-apart parts
follows the action in each part; with a facecam the Short is Split, the game on top and the facecam below.

    python -m unittest discover -s tests/system -t . -p "system_*.py"
"""
import os

os.environ["PITCREW_REAL_MEDIA"] = "1"

from tests import fakes as F  # noqa: E402,F401  (clean settings, throwaway folders)

import subprocess  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

from pipeline import clean_reframe, probe  # noqa: E402
from pipeline.ffmpeg import ffmpeg_exe  # noqa: E402
from pipeline.fonts import prepare_job_fonts  # noqa: E402
from pipeline.game_frame import framing  # noqa: E402
from pipeline.render import render_short  # noqa: E402
from tests.system.system_pipeline import frame_at  # noqa: E402
from tests.system.system_reframe import where  # noqa: E402


class RealGameFraming(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp())
        cls.src = cls.dir / "source.mp4"
        subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                        "color=black:s=1920x1080:d=40:r=30,geq=r='X/W*255':g='Y/H*255':b=128",
                        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", "40", "-c:v", "libx264", "-preset",
                        "ultrafast", "-crf", "12", "-pix_fmt", "yuv444p", "-c:a", "aac", "-shortest", str(cls.src)],
                       check=True, stdin=subprocess.DEVNULL)
        cls.meta = probe(cls.src)
        prepare_job_fonts(cls.dir)

    def make(self, moment, facecam, xs, n):
        cx, rf = framing(moment, xs, self.meta, facecam)
        m = {"hook_mode": "none", **moment, "reframe": clean_reframe(rf, 40)}
        name, _ = render_short(self.src, self.meta, m, [], n, "bold", self.dir, cx=cx)
        out = self.dir / name
        self.assertEqual((probe(out)["width"], probe(out)["height"]), (1080, 1920))
        return out

    def test_a_montage_follows_the_action_in_each_part(self):
        xs = [0.25] * 10 + [0.5] * 15 + [0.75] * 15  # where the motion is: left, middle, right
        out = self.make({"start": 2, "end": 36, "pieces": [[2, 6], [16, 20], [32, 36]]}, None, xs, 1)
        for t, want in ((2.0, 0.25), (6.0, 0.5), (10.0, 0.75)):  # 4 s per part on the Short's clock
            self.assertAlmostEqual(where(frame_at(out, t), 540, 960)[0], want, delta=0.04, msg=t)

    def test_split_puts_the_facecam_below(self):
        cam = {"x0": 0.8, "y0": 0.72, "x1": 0.98, "y1": 0.98}
        out = self.make({"start": 4, "end": 12}, cam, [0.3] * 40, 2)
        img = frame_at(out, 2.0)
        top, bottom = where(img, 540, 480), where(img, 540, 1440)
        self.assertAlmostEqual(top[0], 0.3, delta=0.05)     # the game, centred on the action
        self.assertAlmostEqual(bottom[0], 0.89, delta=0.06)  # the facecam's middle
        self.assertAlmostEqual(bottom[1], 0.85, delta=0.08)


    def test_the_minimap_is_laid_over_the_short(self):
        from pipeline.game_hud import HUD_W, HUD_X, HUD_Y
        out = self.make({"start": 4, "end": 10, "hud": {"minimap": [0.05, 0.755, 0.19, 0.93]}}, None, [0.5] * 40, 3)
        x, y = where(frame_at(out, 2.0), HUD_X + HUD_W // 2, HUD_Y + 60)
        self.assertAlmostEqual(x, 0.12, delta=0.03)  # the middle of the minimap's corner of the game
        self.assertGreater(y, 0.76)


if __name__ == "__main__":
    unittest.main()
