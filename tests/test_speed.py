"""Speed on a small server: what a video's size is (probe) is remembered while the file stays the same, and background
work (making Shorts) runs at a lower priority than the pages, its FFmpeg runs too (web/priority.py)."""
from tests import _env  # noqa: F401  (first: clean settings)

import os
import shutil
import subprocess
import sys
import threading
import time
import unittest
from unittest import mock

from tests import fakes as F


class ProbeIsRemembered(unittest.TestCase):
    def test_same_file_asked_once_a_changed_file_again(self):
        from pipeline import ffmpeg
        d = F.TMP / f"probe-{time.time_ns()}"
        d.mkdir(parents=True)
        v = d / "v.mp4"
        shutil.copy(F.test_video(4), v)
        runs = []
        real = ffmpeg.run
        with mock.patch.object(ffmpeg, "run", lambda cmd, cwd=None: runs.append(cmd) or real(cmd, cwd)):
            a = ffmpeg.probe(v)
            b = ffmpeg.probe(v)
            self.assertEqual(a, b)
            self.assertEqual(len(runs), 1)
            a["width"] = 1  # what it hands out is a copy
            self.assertNotEqual(ffmpeg.probe(v)["width"], 1)
            shutil.copy(F.test_video(6), v)  # another video in its place
            os.utime(v, ns=(time.time_ns(), time.time_ns() + 10**9))
            self.assertAlmostEqual(ffmpeg.probe(v)["duration"], 6, delta=0.2)
            self.assertEqual(len(runs), 2)
        with self.assertRaises(RuntimeError):  # not a video: still an error, every time
            (d / "x.mp4").write_bytes(b"nope")
            ffmpeg.probe(d / "x.mp4")


@unittest.skipUnless(sys.platform.startswith("linux"), "thread priorities are Linux only (the server)")
class BackgroundGivesWay(unittest.TestCase):
    def nice_of(self, fn):
        out = {}

        def run():
            fn()
            out["thread"] = os.getpriority(os.PRIO_PROCESS, threading.get_native_id())
            out["child"] = int(subprocess.run(["sh", "-c", "cut -d' ' -f19 /proc/self/stat"], capture_output=True,
                                              text=True, stdin=subprocess.DEVNULL).stdout)
        t = threading.Thread(target=run)
        t.start()
        t.join()
        return out

    def test_lowered_thread_and_what_it_starts(self):
        from web import priority
        base = os.getpriority(os.PRIO_PROCESS, 0)
        self.assertEqual(self.nice_of(priority.lower), {"thread": max(base, priority.BACKGROUND),
                                                         "child": max(base, priority.BACKGROUND)})
        self.assertEqual(os.getpriority(os.PRIO_PROCESS, threading.get_native_id()), base)  # the rest: unchanged
        self.assertEqual(self.nice_of(lambda: None)["thread"], base)

    def test_shorts_runs_at_the_lower_priority(self):
        from web import priority
        seen = []
        import web.job_queue as Q
        real = Q.run_job
        with mock.patch.object(Q, "run_job", lambda jid: seen.append(os.getpriority(os.PRIO_PROCESS, threading.get_native_id())) or real(jid)):
            F.install()
            F.app()
            c = F.client(F.new_user())
            F.make_shorts(c, 150, 1)
        self.assertEqual(seen, [max(os.getpriority(os.PRIO_PROCESS, 0), priority.BACKGROUND)])


if __name__ == "__main__":
    unittest.main()
