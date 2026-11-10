"""Pause at once: FFmpeg killed mid-run (pipeline.ffmpeg.watching), transcription carrying on from the last word heard
(pipeline/transcribe.py), a helper left behind can't write over the paused job (web/pause.py Run)."""
from tests import _env  # noqa: F401  (first: clean settings)

import importlib
import json
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from pipeline import ffmpeg
from web import pause as P

T = importlib.import_module("pipeline.transcribe")  # (the package's `transcribe` is the function)


class Halt(Exception):
    pass


class FFmpegRun(unittest.TestCase):
    def test_check_kills_a_running_command_at_once(self):
        def check():
            if time.time() - started > 0.2:
                raise Halt()
        started = time.time()
        with ffmpeg.watching(check=check), self.assertRaises(Halt):
            ffmpeg.run(["sleep", "20"])
        self.assertLess(time.time() - started, 2)

    def test_ffmpeg_never_gets_the_terminal(self):
        """stdin is empty on every way in: started from a terminal in the background (update.sh's `timeout`), FFmpeg was
        stopped by the system when it read a key, and the tests on the server hung until they timed out."""
        seen = []
        real_run, real_popen = ffmpeg.subprocess.run, ffmpeg.subprocess.Popen
        with mock.patch.object(ffmpeg.subprocess, "run", side_effect=lambda *a, **k: (seen.append(k.get("stdin")), real_run(*a, **k))[1]), \
             mock.patch.object(ffmpeg.subprocess, "Popen", side_effect=lambda *a, **k: (seen.append(k.get("stdin")), real_popen(*a, **k))[1]):
            ffmpeg.run(["echo", "hi"])
            with ffmpeg.watching(check=lambda: None):
                ffmpeg.run(["echo", "hi"])
        self.assertTrue(len(seen) >= 2 and all(x == ffmpeg.subprocess.DEVNULL for x in seen), seen)  # (run() goes through Popen too)

    def test_watched_run_returns_output_and_reports_failures_as_before(self):
        with ffmpeg.watching(check=lambda: None):
            self.assertEqual(ffmpeg.run(["echo", "hi"]).strip(), "hi")
            with self.assertRaisesRegex(RuntimeError, "Command failed"):
                ffmpeg.run(["sh", "-c", "echo oops >&2; exit 3"])

    def test_progress_reports_how_much_is_made(self):
        seen = []
        script = "for t in 1000000 2500000; do echo out_time_us=$t; done"
        with ffmpeg.watching(on_time=seen.append):
            ffmpeg.run(["sh", "-c", script, "--"])
        self.assertEqual(seen, [])  # -progress is only added for FFmpeg; a plain command is left alone
        real = ffmpeg.ffmpeg_exe()
        with tempfile.TemporaryDirectory() as d, ffmpeg.watching(on_time=seen.append):
            ffmpeg.run([real, "-y", "-f", "lavfi", "-i", "testsrc=d=1:s=64x64:r=10", str(Path(d) / "x.mp4")])
        self.assertTrue(seen and max(seen) > 0.5, seen)


def seg(start, end, *words):
    step = (end - start) / max(len(words), 1)
    ws = [types.SimpleNamespace(word=w, start=start + i * step, end=start + (i + 1) * step) for i, w in enumerate(words)]
    return types.SimpleNamespace(start=start, end=end, words=ws)


class FakeBatched:
    calls = []  # the seconds of audio each run was given

    def __init__(self, model):
        pass

    def transcribe(self, audio, **kw):
        FakeBatched.calls.append(len(audio) / T.SAMPLE_RATE)
        secs = len(audio) / T.SAMPLE_RATE
        return (seg(i, i + 10, f"w{i}") for i in range(0, int(secs), 10)), types.SimpleNamespace(language="en")


class Transcribe(unittest.TestCase):
    def setUp(self):
        FakeBatched.calls = []
        self.dir = tempfile.TemporaryDirectory()
        self.out = Path(self.dir.name) / "transcript.json"
        fw = types.SimpleNamespace(BatchedInferencePipeline=FakeBatched)
        for p in (mock.patch.object(T, "load_audio", lambda v: np.zeros(60 * T.SAMPLE_RATE, dtype=np.float32)),
                  mock.patch.object(T, "whisper_model", lambda n: object()),
                  mock.patch.dict("sys.modules", {"faster_whisper": fw})):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.dir.cleanup)

    def test_a_pause_keeps_the_words_and_the_next_run_listens_from_there(self):
        def pause_at_30(pct, msg):
            if "0:30" in msg:
                raise Halt()
        with self.assertRaises(Halt):
            T.transcribe("v.mp4", self.out, pause_at_30)
        self.assertFalse(self.out.exists())
        self.assertEqual(json.loads(T._partial_path(self.out).read_text())["upto"], 30)
        data = T.transcribe("v.mp4", self.out)
        self.assertEqual(FakeBatched.calls, [60, 30])  # only what was left
        self.assertEqual([w["w"] for w in data["words"]], ["w0", "w10", "w20", "w0", "w10", "w20"])
        self.assertEqual([w["s"] for w in data["words"]], [0, 10, 20, 30, 40, 50])  # on the vlog's clock
        self.assertFalse(T._partial_path(self.out).exists())

    def test_a_pause_is_not_taken_for_the_speech_engine_failing(self):
        with mock.patch.object(T, "print", create=True) as said, self.assertRaises(Halt):
            T.transcribe("v.mp4", self.out, lambda p, m: (_ for _ in ()).throw(Halt()) if "Transcribed" in m else None)
        self.assertFalse([c for c in said.call_args_list if "failed" in str(c)])

    def test_a_run_left_behind_finishes_saving_before_the_next_one_reads(self):
        release, went = threading.Event(), []

        def slow_stop(pct, msg):
            if "0:10" in msg:
                release.wait(5)
                raise Halt()

        def first():
            with self.assertRaises(Halt):
                T.transcribe("v.mp4", self.out, slow_stop)
        a = threading.Thread(target=first)
        a.start()
        time.sleep(0.2)
        b = threading.Thread(target=lambda: went.append(T.transcribe("v.mp4", self.out)))
        b.start()
        time.sleep(0.2)
        self.assertFalse(went)  # waits for the first run
        release.set()
        a.join(5), b.join(5)
        self.assertEqual(FakeBatched.calls, [60, 50])
        self.assertEqual(len(went[0]["words"]), 6)


class RunHelper(unittest.TestCase):
    def tearDown(self):
        P.PAUSING.discard("j1")

    def test_pause_leaves_at_once_and_the_helper_cannot_carry_on(self):
        run, wrote = P.Run("j1"), []

        def slow():
            time.sleep(0.5)
            run.check()  # as its progress reports do
            wrote.append("late")

        threading.Timer(0.1, lambda: P.PAUSING.add("j1")).start()
        started = time.time()
        with self.assertRaises(P.Paused):
            run.doing(slow)
        self.assertLess(time.time() - started, 0.4)
        P.PAUSING.discard("j1")  # the page's state moves on: the helper must still be stopped
        run.helper.join(2)
        self.assertEqual(wrote, [])

    def test_answer_and_error_come_through(self):
        run = P.Run("j1")
        self.assertEqual(run.doing(lambda x: x + 1, 1), 2)
        with self.assertRaises(ValueError):
            run.doing(lambda: (_ for _ in ()).throw(ValueError("x")))


class RemakeProgress(unittest.TestCase):
    def test_the_ring_reads_how_far_the_remake_is_only_for_the_owner(self):
        from tests import fakes as F
        from web import remake_progress as R
        F.install()
        F.reset()
        c = F.client(F.new_user())
        jid, _ = F.make_shorts(c, 60, 1)
        self.assertEqual(c.get(f"/api/remake/{jid}/1").json, {"pct": None})
        with R.tracking(jid, 1, 20) as _:
            with mock.patch.object(ffmpeg, "ffmpeg_exe", lambda: "ffmpeg"):
                ffmpeg._WATCH.on_time(5.0)
        self.assertEqual(c.get(f"/api/remake/{jid}/1").json, {"pct": 25})
        self.assertEqual(F.client(F.new_user()).get(f"/api/remake/{jid}/1").status_code, 404)
        R.done(jid, 1)
        self.assertEqual(c.get(f"/api/remake/{jid}/1").json, {"pct": None})


if __name__ == "__main__":
    unittest.main()
