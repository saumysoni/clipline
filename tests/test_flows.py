"""Whole journeys through the API, the way a creator goes through the pages: several features one after another, with
the state each leaves for the next."""
from tests import fakes as F

import time
import unittest
from datetime import datetime, timedelta

from accounts import db
from settings import JOBS_DIR

CH = "UCchannel000000000000001"


class CreatorJourney(unittest.TestCase):
    def setUp(self):
        F.install()
        F.reset()

    def test_sign_up_to_posted_on_both_apps_to_account_deleted(self):
        c = F.client()
        email = f"journey{time.time_ns()}@example.com"
        self.assertEqual(c.post("/api/auth/signup", json={"email": email, "password": "password-123"}).status_code, 200)
        _, _, text = F.wait_for_mail(email, "Confirm")
        c.post("/api/auth/verify", json={"token": F.link_token(text, "verify")})
        self.assertTrue(c.get("/api/me").json["user"]["verified"])
        uid = db.user_by_email(email)["id"]
        F.connect_youtube(uid, CH, handle="@journey")
        F.connect_instagram(uid)

        # Make Shorts, with a link to the vlog on YouTube for context
        up = F.upload(c, F.test_video(300), piece=256 * 1024)
        r = c.post("/api/start", data={"upload": up, "count": "4", "yt_url": "https://youtu.be/dQw4w9WgXcQ", "tz": "UTC"})
        jid = r.json["id"]
        from web.notices import WATCHING
        st = F.wait(lambda: (j := F.job_json(jid)).get("status") == "ready" and j, timeout=60, what="ready")  # not watching
        F.wait_for_mail(email, "ready")  # away from the page: told by email
        self.assertEqual(len(st["shorts"]), 4)
        self.assertEqual(st["vlog"]["channel_handle"], "@test")  # read from the YouTube link

        # Review: a better hook on one, Try again on another, a caption for Instagram
        c.post(f"/api/hook/{jid}/1", json={"text": "You won't believe this"})
        c.post(f"/api/retry/{jid}/2", json={"note": "the market"})
        c.post(f"/api/clips/{jid}/3/post-text", json={"caption": "Hills, tea and a view. Would you go?"})
        F.wait(lambda: not any(s.get("retrying") for s in F.job_json(jid)["shorts"]), what="edits")

        # Post: YouTube on a schedule, Instagram at the same times; the 4th stays a draft
        start = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        rows = [{"idx": i, "keep": True} for i in (1, 2, 3)]
        self.assertEqual(c.post(f"/api/schedule/{jid}", json={"shorts": rows, "schedule": "custom", "start": start,
                                                              "every": 24, "tz": "UTC", "channel": CH}).status_code, 200)
        F.wait(lambda: F.job_json(jid).get("upload_status") == "done", what="YouTube")
        self.assertEqual(c.post(f"/api/instagram/schedule/{jid}", json={"shorts": rows, "schedule": "same", "tz": "UTC",
                                                                         "yt_schedule": "custom", "yt_start": start}).status_code, 200)
        job = F.job_json(jid)
        yt_times = sorted(u["when"][:16] for u in job["uploads"])
        ig_times = sorted(datetime.fromisoformat(p["when"]).strftime("%Y-%m-%dT%H:%M") for p in job["ig_posts"])
        self.assertEqual(yt_times, ig_times)
        self.assertIn("You won't believe this", F.VIDEOS[next(u for u in job["uploads"] if u["idx"] == 1)["video_id"]]["desc"])
        clips = {c_["idx"]: c_["status"] for c_ in c.get("/api/clips").json["items"]}
        self.assertEqual(clips, {1: "scheduled", 2: "scheduled", 3: "scheduled", 4: "draft"})

        # The day comes: Instagram posts them, YouTube makes them public
        from web import instagram_posting as IPOST
        IPOST._mutate(jid, lambda ps: [dict(p, when=None) for p in ps])
        IPOST._WAKE.set()
        F.wait(lambda: all(p["status"] == "done" for p in F.job_json(jid)["ig_posts"]), what="Reels out")
        self.assertIn("Would you go?", next(r["caption"] for r in F.REELS.values() if "Would you go?" in r["caption"]))
        F.age_uploads(jid, days=(9, 8, 7))
        clips = {c_["idx"]: c_["status"] for c_ in c.get("/api/clips").json["items"]}
        self.assertEqual(clips[1], "posted")

        # Analytics
        y = c.get("/api/analytics?content=shorts&days=28").json["youtube"]
        self.assertGreater(y["totals"]["views"], 0)
        self.assertEqual(len(c.get("/api/analytics/clips").json["clips"]), 3)

        # Delete the vlog's video, then the account
        self.assertEqual(c.post(f"/api/vlogs/{jid}/delete-video").status_code, 200)
        self.assertEqual(c.post("/api/account/delete", json={"email": email}).status_code, 200)
        self.assertFalse((JOBS_DIR / jid).exists())
        self.assertIsNone(db.user_by_email(email))

    def test_vlog_upload_then_shorts_then_restart(self):
        u = F.new_user()
        c = F.client(u)
        F.connect_youtube(u["id"], CH)
        up = F.upload(c, F.test_video(150))
        jid = c.post("/api/vlog/start", data={"upload": up}).json["id"]
        F.wait_ready(c, jid)
        c.post(f"/api/vlog/{jid}/draft", json={"title": "Hills in a day"})
        c.post(f"/api/vlog/{jid}/upload", json={"privacy": "unlisted"})
        F.wait(lambda: F.job_json(jid)["vpost"]["state"] == "done", what="vlog sent")
        c.post(f"/api/vlog/{jid}/shorts", json={"count": 2})
        st = F.wait_ready(c, jid)
        self.assertEqual(len(st["shorts"]), 2)
        self.assertEqual(st["vlog"]["title"], "Hills in a day")
        # Pit Crew restarts: memory is gone, the job comes back from job.json as it was
        from web.store import JOBS, LOCK, load_job
        with LOCK:
            JOBS.pop(jid)
            again = load_job(jid)
        self.assertEqual((again["status"], again["vpost"]["state"], len(again["shorts"])), ("ready", "done", 2))
        v = c.get("/api/vlogs").json["items"][0]
        self.assertEqual(v["id"], jid)

    def test_two_creators_never_see_each_other(self):
        a, b = F.new_user(), F.new_user()
        ca, cb = F.client(a), F.client(b)
        ja, _ = F.make_shorts(ca, 60, 1)
        jb, _ = F.make_shorts(cb, 90, 1)
        self.assertEqual([v["id"] for v in ca.get("/api/vlogs").json["items"]], [ja])
        self.assertEqual({c["job"] for c in cb.get("/api/clips").json["items"]}, {jb})
        F.connect_youtube(a["id"], CH)
        self.assertFalse(cb.get("/api/youtube/me").json.get("signed_in"))


if __name__ == "__main__":
    unittest.main()
