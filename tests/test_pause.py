"""Pause and Resume while Shorts are being made (web/pause.py, web/make_shorts.py): paused after the current step,
waiting vlogs at once, the spot goes to the next vlog, Resume skips what's done, Stop and retention on a paused vlog."""
from tests import _env  # noqa: F401  (first: clean settings)

import time
import unittest

from tests import fakes as F
from settings import JOBS_DIR


class Pause(unittest.TestCase):
    def setUp(self):
        F.install()
        F.reset()
        self.c = F.client(F.new_user())

    def tearDown(self):
        F.SLOW.transcribe, F.SLOW.render = 0, 0

    def start(self, c=None, seconds=60, count=1):
        c = c or self.c
        up = F.upload(c, F.test_video(seconds))
        return c.post("/api/start", data={"upload": up, "count": str(count)}).json["id"]

    def wait_status(self, jid, status):
        return F.wait(lambda: (j := F.job_json(jid)).get("status") == status and j, timeout=30, what=status)

    def test_pause_after_transcribing_frees_the_spot_and_resumes(self):
        F.SLOW.transcribe = 1.0
        first, second = self.start(), self.start()  # one at a time per creator: the second waits
        F.wait(lambda: F.job_json(first).get("stage") == 1, what="transcribing")
        r = self.c.post(f"/api/vlogs/{first}/pause")
        self.assertEqual(r.json, {"ok": True, "paused": False})  # after this step
        self.assertTrue(self.c.get(f"/api/status/{first}").json["pausing"])
        j = self.wait_status(first, "paused")
        self.assertEqual(j["stage"], 1)  # transcribing finished, finding moments didn't start
        self.assertTrue((JOBS_DIR / first / "transcript.json").exists())
        self.assertNotIn("moments", F.AI.kinds())
        F.SLOW.transcribe = 0
        self.assertEqual(F.wait_ready(self.c, second)["status"], "ready")  # its spot went to the other vlog
        item = next(v for v in self.c.get("/api/vlogs").json["items"] if v["id"] == first)
        self.assertEqual(item["status"], "paused")
        self.assertEqual(self.c.post(f"/api/vlogs/{first}/pause").json, {"ok": True, "paused": True})  # twice: fine
        moments_before = F.AI.kinds().count("moments")
        self.assertEqual(self.c.post(f"/api/vlogs/{first}/resume").status_code, 200)
        st = F.wait_ready(self.c, first)
        self.assertEqual(st["status"], "ready")
        self.assertEqual(len(st["shorts"]), 1)
        self.assertEqual(F.AI.kinds().count("moments"), moments_before + 1)
        self.assertFalse(st.get("plan") or st.get("made") or st.get("pausing"))
        self.assertEqual(self.c.post(f"/api/vlogs/{first}/resume").status_code, 400)  # not paused any more

    def test_pause_while_editing_keeps_the_shorts_made(self):
        F.SLOW.render = 0.6
        jid = self.start(seconds=150, count=3)
        F.wait(lambda: F.job_json(jid).get("stage") == 3, timeout=30, what="editing")
        self.c.post(f"/api/vlogs/{jid}/pause")
        j = self.wait_status(jid, "paused")
        made = [d["i"] for d in j["made"]]
        self.assertTrue(1 <= len(made) < 3, made)
        self.assertEqual(len(j["plan"]), 3)
        F.RENDERED.clear()
        kinds = len(F.AI.kinds())
        F.SLOW.render = 0
        self.c.post(f"/api/vlogs/{jid}/resume")
        st = F.wait_ready(self.c, jid)
        self.assertEqual(st["status"], "ready")
        self.assertEqual([s["idx"] for s in st["shorts"]], [1, 2, 3])
        self.assertEqual(sorted(r["idx"] for r in F.RENDERED), [i for i in (1, 2, 3) if i not in made])  # only the rest
        self.assertNotIn("moments", F.AI.kinds()[kinds:])  # the moments chosen before are kept
        self.assertTrue(all((JOBS_DIR / jid / s["thumb"]).exists() for s in st["shorts"]))

    def test_pause_while_waiting_is_at_once(self):
        F.SLOW.transcribe = 1.5
        running, waiting = self.start(), self.start()
        F.wait(lambda: F.job_json(running).get("stage") == 1, what="running")
        self.assertEqual(self.c.post(f"/api/vlogs/{waiting}/pause").json, {"ok": True, "paused": True})
        j = F.job_json(waiting)
        self.assertEqual((j["status"], j["queued"]), ("paused", False))
        F.SLOW.transcribe = 0
        F.wait_ready(self.c, running)
        time.sleep(0.5)
        self.assertEqual(F.job_json(waiting)["status"], "paused")  # the queue doesn't start it
        self.c.post(f"/api/vlogs/{waiting}/resume")
        self.assertEqual(F.wait_ready(self.c, waiting)["status"], "ready")

    def test_resume_before_the_pause_happened_just_carries_on(self):
        F.SLOW.transcribe = 1.0
        jid = self.start()
        F.wait(lambda: F.job_json(jid).get("stage") == 1, what="running")
        self.c.post(f"/api/vlogs/{jid}/pause")
        self.assertEqual(self.c.post(f"/api/vlogs/{jid}/resume").status_code, 200)
        F.SLOW.transcribe = 0
        st = F.wait_ready(self.c, jid)
        self.assertEqual(st["status"], "ready")
        self.assertFalse(st.get("pausing"))

    def test_stop_a_paused_vlog(self):
        F.SLOW.transcribe = 1.0
        jid = self.start()
        F.wait(lambda: F.job_json(jid).get("stage") == 1, what="running")
        self.c.post(f"/api/vlogs/{jid}/pause")
        self.wait_status(jid, "paused")
        self.assertEqual(self.c.post(f"/api/vlogs/{jid}/stop").status_code, 200)
        self.assertFalse((JOBS_DIR / jid).exists())
        self.assertEqual(self.c.get("/api/vlogs").json["items"], [])

    def test_only_shorts_runs_of_your_own(self):
        F.SLOW.transcribe = 1.0
        jid = self.start()
        other = F.client(F.new_user())
        self.assertEqual(other.post(f"/api/vlogs/{jid}/pause").status_code, 404)
        self.assertEqual(other.post(f"/api/vlogs/{jid}/resume").status_code, 404)
        F.SLOW.transcribe = 0
        F.wait_ready(self.c, jid)
        self.assertEqual(self.c.post(f"/api/vlogs/{jid}/pause").status_code, 400)  # finished
        self.assertEqual(self.c.post(f"/api/vlogs/{jid}/resume").status_code, 400)

    def test_a_paused_vlog_is_kept_like_a_stopped_one(self):
        from web import retention
        from web.store import JOBS, LOCK
        F.SLOW.transcribe = 1.0
        jid = self.start()
        F.wait(lambda: F.job_json(jid).get("stage") == 1, what="running")
        self.c.post(f"/api/vlogs/{jid}/pause")
        self.wait_status(jid, "paused")
        self.assertIn("paused", self.c.post(f"/api/vlogs/{jid}/delete-video").json["error"])
        self.assertEqual(retention.sweep_job(jid), [])  # not yet
        with LOCK:
            JOBS[jid]["last_edit_at"] = time.time() - retention.keep_original() - 10
        retention.sweep_job(jid)
        self.assertFalse((JOBS_DIR / jid).exists())  # nothing was made: removed completely, like a stopped vlog


if __name__ == "__main__":
    unittest.main()
