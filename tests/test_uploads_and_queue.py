"""Sending a video in pieces, starting a vlog, limits, the queue, Stop / Try again and picking up after a restart
(web/video_upload.py, web/make_shorts.py, web/allowance.py, web/job_queue.py, web/stop_and_retry.py, web/store.py)."""
from tests import fakes as F

import json
import os
import time
import unittest

from accounts import db
from settings import JOBS_DIR


class Pieces(unittest.TestCase):
    def setUp(self):
        F.install()
        F.reset()
        self.u = F.new_user()
        self.c = F.client(self.u)

    def new(self, size, name="trip.MOV"):
        return self.c.post("/api/upload/new", json={"name": name, "size": size})

    def test_in_order_repeats_gaps_and_resume(self):
        data = os.urandom(3000)
        uid = self.new(len(data)).get_json()["id"]
        put = lambda off, chunk: self.c.post(f"/api/upload/{uid}?offset={off}", data=chunk)  # noqa: E731
        self.assertEqual(put(0, data[:1000]).get_json()["received"], 1000)
        self.assertEqual(put(0, data[:1000]).get_json()["received"], 1000)  # a repeat writes nothing
        gap = put(2000, data[2000:])
        self.assertEqual(gap.status_code, 409)
        self.assertEqual(gap.get_json()["received"], 1000)
        self.assertEqual(self.c.get(f"/api/upload/{uid}").get_json(), {"received": 1000, "size": 3000})
        self.assertEqual(put(1000, data[1000:] + b"extra bytes past the end").get_json()["received"], 3000)
        from web.video_upload import UPLOADS_DIR
        self.assertEqual((UPLOADS_DIR / uid / "data").read_bytes(), data)

    def test_refusals(self):
        self.assertEqual(self.new(0).status_code, 400)
        os.environ["MAX_UPLOAD_GB"] = "0.1"  # (the smallest it can be set to)
        try:
            r = self.new(200_000_000)
            self.assertEqual(r.status_code, 400)
            self.assertIn("GB", r.get_json()["error"])
        finally:
            os.environ.pop("MAX_UPLOAD_GB")
        uid = self.new(10).get_json()["id"]
        other = F.client(F.new_user())
        self.assertEqual(other.get(f"/api/upload/{uid}").status_code, 404)
        self.assertEqual(other.post(f"/api/upload/{uid}?offset=0", data=b"x").status_code, 404)
        self.assertEqual(self.c.get("/api/upload/../../etc").status_code, 404)

    def test_monthly_allowance_used_up(self):
        os.environ["MONTHLY_VLOG_MINUTES"] = "1"
        try:
            from web.allowance import _month
            db.add_usage(self.u["id"], _month(), 60)
            r = self.new(1000)
            self.assertEqual(r.status_code, 403)
            self.assertIn("this month", r.get_json()["error"])
            self.assertEqual(self.c.get("/api/allowance").get_json()["used"], 1.0)
        finally:
            os.environ.pop("MONTHLY_VLOG_MINUTES")

    def test_many_uploads_starting_at_once_keep_each_other(self):
        """Found by the stress test: one creator's clean-up deleted others' uploads that were just being created."""
        import threading
        from web.video_upload import UPLOADS_DIR
        clients = [F.client(F.new_user()) for _ in range(12)]
        ids, errors = [], []

        def go(c):
            for _ in range(5):
                r = c.post("/api/upload/new", json={"name": "v.mp4", "size": 10})
                if r.status_code != 200:
                    errors.append(r.status_code)
                    continue
                uid = r.json["id"]
                ids.append(uid)
                if c.post(f"/api/upload/{uid}?offset=0", data=b"0123456789").status_code != 200:
                    errors.append("piece")
        threads = [threading.Thread(target=go, args=(c,)) for c in clients]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertTrue(all((UPLOADS_DIR / i / "data").stat().st_size == 10 for i in ids))

    def test_stale_uploads_cleaned(self):
        from web.video_upload import UPLOADS_DIR
        old = self.new(10).get_json()["id"]
        meta = json.loads((UPLOADS_DIR / old / "meta.json").read_text())
        meta["touched"] = time.time() - 25 * 3600
        (UPLOADS_DIR / old / "meta.json").write_text(json.dumps(meta))
        self.new(10)
        self.assertFalse((UPLOADS_DIR / old).exists())


class Start(unittest.TestCase):
    def setUp(self):
        F.install()
        F.reset()
        self.u = F.new_user()
        self.c = F.client(self.u)

    def test_checks_before_starting(self):
        r = self.c.post("/api/start", data={"count": "3"})
        self.assertEqual(r.status_code, 400)
        r = self.c.post("/api/start", data={"link": "https://example.com/video.mp4"})
        self.assertEqual(r.json["field"], "link")
        up = F.upload(self.c, F.test_video(60))
        r = self.c.post("/api/start", data={"upload": up, "must": json.dumps([{"start": "1:00", "end": "0:30"}])})
        self.assertEqual(r.json["field"], "must")
        r = self.c.post("/api/start", data={"upload": up, "yt_url": "https://vimeo.com/123"})
        self.assertEqual(r.json["field"], "yt_url")
        r = self.c.post("/api/start", data={"upload": up, "count": "1"})  # the upload stayed for the fixed form
        self.assertEqual(r.status_code, 200)

    def test_not_a_video(self):
        from web.video_upload import UPLOADS_DIR
        uid = self.c.post("/api/upload/new", json={"name": "notes.txt", "size": 5}).json["id"]
        self.c.post(f"/api/upload/{uid}?offset=0", data=b"hello")
        r = self.c.post("/api/start", data={"upload": uid})
        self.assertEqual(r.status_code, 400)
        self.assertTrue(r.json["upload_gone"])
        self.assertFalse((UPLOADS_DIR / uid).exists())

    def test_too_long(self):
        os.environ["MAX_VLOG_MINUTES"] = "0.5"
        try:
            up = F.upload(self.c, F.test_video(60))
            r = self.c.post("/api/start", data={"upload": up})
            self.assertEqual(r.status_code, 400)
            self.assertIn("long", r.json["error"])
        finally:
            os.environ.pop("MAX_VLOG_MINUTES")

    def test_result_and_charge_once(self):
        jid, st = F.make_shorts(self.c, 150, 3, title="Hill day", note="Funny bits please")
        self.assertEqual(len(st["shorts"]), 3)
        for s in st["shorts"]:
            for f in (s["video"], s["thumb"], f"captions_{s['idx']}.ass"):
                self.assertTrue((JOBS_DIR / jid / f).exists(), f)
            self.assertTrue(15 <= s["end"] - s["start"] <= 59)
            self.assertIn("edited_at", s)
        self.assertEqual(st["charged"], 150)
        from web.allowance import _month
        self.assertAlmostEqual(db.used_seconds(self.u["id"], _month()), 150, delta=1)
        prompt = next(k for k, _ in F.AI.calls)
        self.assertEqual(prompt, "moments")

    def test_must_have_moments_come_first(self):
        jid, st = F.make_shorts(self.c, 150, 2, must=json.dumps([{"start": "1:40", "end": "2:05"}]))
        first = st["shorts"][0]
        self.assertAlmostEqual(first["start"], 100, delta=1)
        self.assertAlmostEqual(first["end"], 125, delta=1)
        self.assertIn("manual", F.AI.kinds())

    def test_ai_failure_is_one_plain_sentence(self):
        F.AI.fail(401, "API key not valid", times=20)
        up = F.upload(self.c, F.test_video(60))
        jid = self.c.post("/api/start", data={"upload": up, "count": "1"}).json["id"]
        st = F.wait_ready(self.c, jid)
        self.assertEqual(st["status"], "error")
        self.assertNotIn("401", st["error"])
        self.assertNotIn("key", st["error"].lower().replace("try again", ""))
        self.assertTrue(F.job_json(jid)["error_detail"])  # the detail is kept for us, not shown

    def test_transcript_remembered_for_the_same_video(self):
        from pipeline.transcript_cache import find_saved_transcript
        first, _ = F.make_shorts(self.c, 90, 1)
        saved = find_saved_transcript(F.test_video(90))
        self.assertIsNotNone(saved)
        jid, _ = F.make_shorts(self.c, 90, 1)
        self.assertEqual((JOBS_DIR / jid / "transcript.json").read_text(), saved.read_text())


class QueueAndStop(unittest.TestCase):
    def setUp(self):
        F.install()
        F.reset()

    def start(self, c, seconds=60):
        up = F.upload(c, F.test_video(seconds))
        return c.post("/api/start", data={"upload": up, "count": "1"}).json["id"]

    def test_one_at_a_time_per_creator_and_fair_slots(self):
        import web.job_queue as Q
        a, b = F.client(F.new_user()), F.client(F.new_user())
        F.SLOW.transcribe = 1.0
        try:
            a1, a2 = self.start(a), self.start(a)
            b1 = self.start(b)
            F.wait(lambda: F.job_json(a1).get("stage") == 1 and F.job_json(b1).get("stage") == 1, what="two running")
            j2 = F.job_json(a2)
            self.assertTrue(j2["queued"])
            self.assertEqual(j2["msg"], "Starts after your other vlog")
            self.assertLessEqual(len(Q.RUNNING), Q.SLOTS)
        finally:
            F.SLOW.transcribe = 0
        for jid in (a1, a2, b1):
            self.assertEqual(F.wait_ready(a if jid != b1 else b, jid)["status"], "ready")

    def test_stop_while_waiting_and_while_running(self):
        c = F.client(F.new_user())
        F.SLOW.transcribe = 5
        try:
            running, waiting = self.start(c), self.start(c)
            F.wait(lambda: F.job_json(running).get("stage") == 1, what="running")
            self.assertEqual(c.post(f"/api/vlogs/{waiting}/stop").status_code, 200)
            self.assertFalse((JOBS_DIR / waiting).exists())
            self.assertEqual(c.post(f"/api/vlogs/{running}/stop").status_code, 200)
            F.wait(lambda: not (JOBS_DIR / running).exists(), what="stopped")
        finally:
            F.SLOW.transcribe = 0
        self.assertEqual(c.get("/api/vlogs").json["items"], [])

    def test_try_again_after_an_error(self):
        c = F.client(F.new_user())
        F.SLOW.fail = "the video editor stopped"
        jid = self.start(c)
        st = F.wait_ready(c, jid)
        self.assertEqual(st["status"], "error")
        F.SLOW.fail = ""
        self.assertEqual(c.post(f"/api/vlogs/{jid}/again").status_code, 200)
        self.assertEqual(F.wait_ready(c, jid)["status"], "ready")
        self.assertEqual(c.post(f"/api/vlogs/{jid}/again").status_code, 400)  # not stopped any more

    def test_restart_queues_unfinished_vlogs_again(self):
        from web.store import JOBS, LOCK, RECOVERED, load_job
        u = F.new_user()
        c = F.client(u)
        jid, _ = F.make_shorts(c, 60, 1)
        with LOCK:
            job = dict(JOBS.pop(jid))
        job.update(status="working", queued=False, stage=3)
        (JOBS_DIR / jid / "job.json").write_text(json.dumps(job))
        with LOCK:
            again = load_job(jid)
        self.assertEqual(again["status"], "working")
        self.assertTrue(again["queued"])
        self.assertEqual(again["recoveries"], 1)
        self.assertEqual(F.wait_ready(c, jid)["status"], "ready")  # the queue picked it up
        # the third crash in a row: stays stopped, so one bad vlog can't bring Pit Crew down forever
        with LOCK:
            job = dict(JOBS.pop(jid))
        job.update(status="working", queued=False, recoveries=2)
        (JOBS_DIR / jid / "job.json").write_text(json.dumps(job))
        with LOCK:
            stuck = load_job(jid)
        self.assertEqual(stuck["status"], "error")
        self.assertIn("restarted", stuck["error"])
        self.assertNotIn(jid, RECOVERED)


if __name__ == "__main__":
    unittest.main()
