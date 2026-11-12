"""
System test of the quick ways Pit Crew reads a vlog, with the real FFmpeg (they count most on a small server):
the face finder reads only the keyframes when a phone put enough of them (pipeline/reframe.py), the long way otherwise;
Auto layout's search for new shots stops at the end of the Short's part instead of reading on to the end of the vlog
(pipeline/smart_reframe.py scene_changes).

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


if __name__ == "__main__":
    unittest.main()
