"""Storage deleted on a timer (web/retention.py), the public pages, /healthz, the page itself and its media
(web/legal.py, web/health.py, web/pages.py)."""
from tests import fakes as F

import os
import time
import unittest

from settings import JOBS_DIR
from web import retention as R

DAY = 86400


class Retention(unittest.TestCase):
    def setUp(self):
        F.install()
        F.reset()
        self.u = F.new_user()
        self.c = F.client(self.u)
        self.jid, self.st = F.make_shorts(self.c, 150, 3)
        self.job = F.job_json(self.jid)

    def test_vlog_video_warned_a_day_before_then_deleted(self):
        exp = R.video_expires(self.job)
        self.assertAlmostEqual(exp - self.job["last_edit_at"], 72 * 3600, delta=1)
        self.assertEqual(R.sweep_job(self.jid, exp - 2 * DAY), [])
        self.assertIn("video warning", R.sweep_job(self.jid, exp - 3600))
        F.wait_for_mail(self.u["email"], "will be deleted")
        self.assertNotIn("video warning", R.sweep_job(self.jid, exp - 1800))  # warned once
        self.assertIn("video deleted", R.sweep_job(self.jid, exp + 1))
        self.assertFalse(list((JOBS_DIR / self.jid).glob("source.*")))
        self.assertTrue((JOBS_DIR / self.jid / self.st["shorts"][0]["video"]).exists())  # the Shorts stay

    def test_an_edit_restarts_the_clock(self):
        from web.store import update_short
        before = R.video_expires(self.job)
        time.sleep(0.05)
        update_short(self.jid, 1, title="edited")
        self.assertGreater(R.video_expires(F.job_json(self.jid)), before)

    def test_drafts_deleted_after_30_days_posted_ones_kept(self):
        F.connect_youtube(self.u["id"])
        self.c.post(f"/api/schedule/{self.jid}", json={"shorts": [{"idx": 1, "keep": True}], "schedule": "now"})
        F.wait(lambda: F.job_json(self.jid).get("upload_status") == "done", what="posted")
        job = F.job_json(self.jid)
        exp = R.draft_expires(job, job["shorts"][1])
        self.assertIsNone(R.draft_expires(job, job["shorts"][0]))
        done = R.sweep_job(self.jid, exp + 1)
        self.assertIn("draft 2 deleted", done)
        self.assertIn("draft 3 deleted", done)
        self.assertEqual([s["idx"] for s in F.job_json(self.jid)["shorts"]], [1])

    def test_posted_file_deleted_30_days_after_it_went_out(self):
        F.connect_youtube(self.u["id"])
        self.c.post(f"/api/schedule/{self.jid}", json={"shorts": [{"idx": 1, "keep": True}], "schedule": "now"})
        F.wait(lambda: F.job_json(self.jid).get("upload_status") == "done", what="posted")
        job = F.job_json(self.jid)
        fexp = R.file_expires(job, job["shorts"][0])
        self.assertIn("posted file 1 deleted", R.sweep_job(self.jid, fexp + 1))
        s = F.job_json(self.jid)["shorts"][0]
        self.assertTrue(s["file_deleted_at"])
        self.assertTrue((JOBS_DIR / self.jid / s["thumb"]).exists())  # its thumbnail and record stay

    def test_nothing_touched_while_busy_and_zero_keeps_forever(self):
        from web.posting import POSTING
        POSTING.add(self.jid)
        try:
            self.assertEqual(R.sweep_job(self.jid, time.time() + 400 * DAY), [])
        finally:
            POSTING.discard(self.jid)
        os.environ["KEEP_ORIGINAL_HOURS"] = "0"
        os.environ["KEEP_DRAFT_DAYS"] = "0"
        try:
            self.assertEqual(R.sweep_job(self.jid, time.time() + 400 * DAY), [])
        finally:
            del os.environ["KEEP_ORIGINAL_HOURS"], os.environ["KEEP_DRAFT_DAYS"]

    def test_saved_transcripts(self):
        from pipeline.transcript_cache import TRANSCRIPTS_DIR
        self.assertTrue(list(TRANSCRIPTS_DIR.glob("*.json")))
        self.assertGreaterEqual(R.sweep_transcripts(time.time() + 31 * DAY), 1)
        self.assertFalse(list(TRANSCRIPTS_DIR.glob("*.json")))
        self.assertTrue((JOBS_DIR / self.jid / "transcript.json").exists())  # the vlog's own copy stays

    def test_stopped_vlog_with_nothing_kept_is_removed(self):
        F.SLOW.fail = "editor stopped"
        up = F.upload(self.c, F.test_video(60))
        jid = self.c.post("/api/start", data={"upload": up, "count": "1"}).json["id"]
        F.wait_ready(self.c, jid)
        F.SLOW.fail = ""
        self.assertIn("stopped vlog removed", R.sweep_job(jid, time.time() + 73 * 3600))
        self.assertFalse((JOBS_DIR / jid).exists())


class Pages(unittest.TestCase):
    def setUp(self):
        F.install()
        F.reset()

    def test_public_pages_filled_in(self):
        c = F.client()
        for path in ("/welcome", "/privacy", "/terms", "/data-deletion"):
            r = c.get(path)
            self.assertEqual(r.status_code, 200, path)
            text = r.get_data(as_text=True)
            self.assertNotIn("{{", text, path)
            self.assertIn("help@pitcrew.test", text + c.get("/privacy").get_data(as_text=True))
        privacy = c.get("/privacy").get_data(as_text=True)
        self.assertIn("72 hours", privacy)
        self.assertIn("30 days", privacy)
        self.assertIn("Gemini", privacy)
        self.assertEqual(c.get("/legal-nope").status_code, 404)

    def test_privacy_follows_the_settings(self):
        os.environ["KEEP_ORIGINAL_HOURS"] = "48"
        try:
            self.assertIn("48 hours", F.client().get("/privacy").get_data(as_text=True))
        finally:
            del os.environ["KEEP_ORIGINAL_HOURS"]

    def test_healthz(self):
        r = F.client().get("/healthz")
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        self.assertTrue(r.json["ok"])

    def test_page_and_config(self):
        c = F.client()
        r = c.get("/")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn("<script", html)
        self.assertNotIn("<!-- include", html)  # every section filled in
        cfg = c.get("/api/config").json
        self.assertEqual(cfg.get("support"), "help@pitcrew.test") if "support" in cfg else None
        self.assertEqual(c.get("/static/js/core.js").status_code, 200)

    def test_media_is_private_and_safe(self):
        u = F.new_user()
        c = F.client(u)
        jid, st = F.make_shorts(c, 60, 1)
        self.assertEqual(c.get(f"/media/{jid}/{st['shorts'][0]['thumb']}").status_code, 200)
        for bad in ("../../data/test.db", "..%2f..%2fdata%2ftest.db", "job.json", "/etc/passwd"):
            r = c.get(f"/media/{jid}/{bad}", follow_redirects=True)
            self.assertIn(r.status_code, (403, 404), bad)
        self.assertEqual(F.client().get(f"/media/{jid}/{st['shorts'][0]['thumb']}").status_code, 401)


if __name__ == "__main__":
    unittest.main()
