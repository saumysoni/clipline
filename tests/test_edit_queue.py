"""Edits saved in the editor take turns on the whole server (web/edit_queue.py): with five vlogs' Shorts saved at once
only SLOTS render together, the others say they're waiting and then finish, a failed render gives its turn back, and
different kinds of edits (captions, Trim, a hook, Try again) share the same turns."""
from tests import _env  # noqa: F401  (first: clean settings)

import threading
import time
import unittest

import pipeline
from tests import fakes as F


class EditsTakeTurns(unittest.TestCase):
    def setUp(self):
        from web import edit_queue
        F.install()
        F.reset()
        self.c = F.client(F.new_user())
        self.vlogs = [F.make_shorts(self.c, 150, 1) for _ in range(5)]
        self.Q = edit_queue
        self._turns, edit_queue._TURNS = edit_queue._TURNS, threading.BoundedSemaphore(2)  # as on a 4-core server
        self.now = self.most = 0
        self.lock = threading.Lock()
        real = pipeline.render_short

        def counted(*a, **kw):
            with self.lock:
                self.now += 1
                self.most = max(self.most, self.now)
            try:
                return real(*a, **kw)
            finally:
                with self.lock:
                    self.now -= 1
        self._real, pipeline.render_short = real, counted
        F.SLOW.render = 0.6

    def tearDown(self):
        F.SLOW.render = 0
        pipeline.render_short = self._real
        self.Q._TURNS = self._turns

    def short(self, jid):
        return F.job_json(jid)["shorts"][0]

    def done(self, jid):
        return F.wait(lambda: (s := self.short(jid)) and not s.get("retrying") and s, timeout=60, what="edit done")

    def test_five_saves_at_once_two_render_the_rest_wait_then_finish(self):
        before = {jid: st["shorts"][0]["video"] for jid, st in self.vlogs}
        for jid, st in self.vlogs:
            r = self.c.post(f"/api/captions/{jid}/{st['shorts'][0]['idx']}", json={"captions": {"preset": "pop"}, "remake": True})
            self.assertEqual(r.status_code, 200)
        F.wait(lambda: len(self.Q.WAITING) == 3, timeout=10, what="three waiting")
        waiting = [jid for jid, _ in self.vlogs if self.short(jid).get("retry_msg") == self.Q.WAITING_MSG]
        self.assertEqual(len(waiting), 3)  # the page says so on those Shorts
        for jid, _ in self.vlogs:
            s = self.done(jid)
            self.assertFalse(s.get("retry_error"), s)
            self.assertNotEqual(s["video"], before[jid])  # made again
            self.assertFalse(s.get("retry_msg"))
        self.assertEqual(self.most, 2)
        self.assertEqual(self.Q.WAITING, [])
        self.assertTrue(self.Q._TURNS.acquire(blocking=False) and self.Q._TURNS.acquire(blocking=False))  # all given back
        self.Q._TURNS.release()
        self.Q._TURNS.release()

    def test_a_failed_render_gives_its_turn_back(self):
        real = pipeline.render_short
        calls = []

        def first_fails(*a, **kw):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("FFmpeg stopped")
            return real(*a, **kw)
        pipeline.render_short = first_fails
        self.Q._TURNS = threading.BoundedSemaphore(1)
        (a, sa), (b, sb) = self.vlogs[:2]
        self.c.post(f"/api/captions/{a}/{sa['shorts'][0]['idx']}", json={"captions": {"preset": "pop"}, "remake": True})
        self.c.post(f"/api/captions/{b}/{sb['shorts'][0]['idx']}", json={"captions": {"preset": "pop"}, "remake": True})
        results = sorted([bool(self.done(a).get("retry_error")), bool(self.done(b).get("retry_error"))])
        self.assertEqual(results, [False, True])  # one failed, the other still got its turn
        self.assertTrue(self.Q._TURNS.acquire(blocking=False))
        self.Q._TURNS.release()

    def test_every_kind_of_edit_shares_the_turns(self):
        jobs = [(jid, st["shorts"][0]) for jid, st in self.vlogs[:4]]
        (j1, s1), (j2, s2), (j3, s3), (j4, s4) = jobs
        start, end = s4["start"], s4["end"]
        rs = [self.c.post(f"/api/captions/{j1}/{s1['idx']}", json={"captions": {"preset": "pop"}, "remake": True}),
              self.c.post(f"/api/hook/{j2}/{s2['idx']}", json={"mode": "text", "text": "Wait for it"}),
              self.c.post(f"/api/retry/{j3}/{s3['idx']}", json={}),
              self.c.post(f"/api/ai-edit/{j4}/{s4['idx']}/apply", json={"pieces": [[start + 1, end - 1]]})]
        self.assertEqual([r.status_code for r in rs], [200] * 4, [r.get_json() for r in rs])
        self.assertFalse(any((r.get_json() or {}).get("unchanged") for r in rs))
        F.wait(lambda: len(self.Q.WAITING) >= 1, timeout=10, what="one waiting")
        for jid, s in jobs:
            done = self.done(jid)
            self.assertFalse(done.get("retry_error"), done)
            self.assertNotEqual(done["video"], s["video"])
        self.assertEqual(self.most, 2)
        self.assertEqual(self.Q.WAITING, [])


if __name__ == "__main__":
    unittest.main()
