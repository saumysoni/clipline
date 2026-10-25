"""Instagram: connecting (Instagram login), several accounts, planning Reels, the scheduler posting them, failures,
Try again / Cancel, the signed video link Instagram downloads from (instagram/, web/instagram_connect.py,
web/instagram_posting.py)."""
from tests import fakes as F

import time
import unittest
import urllib.parse
from datetime import datetime, timedelta, timezone

from accounts import db


class Connect(unittest.TestCase):
    def setUp(self):
        F.install()
        F.reset()
        self.u = F.new_user()
        self.c = F.client(self.u)

    def login(self, code="good", **extra):
        r = self.c.get("/api/instagram/signin?popup=1")
        self.assertEqual(r.status_code, 302)
        q = urllib.parse.parse_qs(urllib.parse.urlparse(r.headers["Location"]).query)
        self.assertIn("instagram_business_content_publish", q["scope"][0])
        return F.client().get("/api/instagram/callback?" + urllib.parse.urlencode(
            {"code": code + "#_", "state": q["state"][0], **extra}))  # Instagram's redirect comes in another tab

    def test_full_sign_in(self):
        r = self.login()
        self.assertEqual(r.status_code, 200)
        me = self.c.get("/api/instagram/me").json
        self.assertTrue(me["signed_in"])
        self.assertEqual(me["username"], "pitcrew.test")
        self.assertTrue(me["can_post"])
        self.assertGreater(me["days_left"], 55)
        token = db.connection(self.u["id"], "instagram")["token"]["token"]
        self.assertEqual(token, "long-token")  # the 60-day token, not the short one

    def test_state_is_used_once_and_cancel_and_missing_permission(self):
        r = self.c.get("/api/instagram/signin")
        state = urllib.parse.parse_qs(urllib.parse.urlparse(r.headers["Location"]).query)["state"][0]
        F.client().get(f"/api/instagram/callback?code=x&state={state}")
        r = F.client().get(f"/api/instagram/callback?code=x&state={state}")
        self.assertIn("out of date", r.get_data(as_text=True))
        r = self.login(error="access_denied", error_reason="user_denied")
        self.assertIn("cancelled", r.get_data(as_text=True))
        F.IG.permissions = "instagram_business_basic"
        r = self.login()
        self.assertIn("permission to publish", r.get_data(as_text=True))

    def test_personal_account_cant_be_posted_to(self):
        F.IG.account_type = "PERSONAL"
        self.login()
        self.assertFalse(self.c.get("/api/instagram/me").json["can_post"])

    def test_token_refreshed_when_close_to_expiring_and_dropped_when_expired(self):
        F.connect_instagram(self.u["id"], days_left=5)
        self.assertTrue(self.c.get("/api/instagram/me").json["signed_in"])
        self.assertEqual(F.IG.refreshed, 1)
        F.connect_instagram(self.u["id"], "999", days_left=-1)
        self.c.post("/api/instagram/switch", json={"ig_id": "999"})
        me = self.c.get("/api/instagram/me").json
        self.assertIsNone(db.connection(self.u["id"], "instagram", "999"))  # the expired one is gone
        self.assertEqual(me["ig_id"], "1789")  # the one that's still valid is used again

    def test_several_accounts(self):
        F.connect_instagram(self.u["id"], "111", "first")
        F.connect_instagram(self.u["id"], "222", "second")
        self.assertEqual(self.c.get("/api/instagram/me").json["username"], "second")
        self.assertEqual(self.c.post("/api/instagram/switch", json={"ig_id": "111"}).json["username"], "first")
        self.assertEqual(self.c.post("/api/instagram/switch", json={"ig_id": "333"}).status_code, 400)
        me = self.c.post("/api/instagram/signout", json={"ig_id": "111"}).json
        self.assertEqual([a["username"] for a in me["accounts"]], ["second"])


class Posting(unittest.TestCase):
    def setUp(self):
        F.install()
        F.reset()
        self.u = F.new_user()
        self.c = F.client(self.u)
        self.jid, self.st = F.make_shorts(self.c, 150, 3)
        F.connect_instagram(self.u["id"])

    def plan(self, idxs=(1,), schedule="now", **extra):
        return self.c.post(f"/api/instagram/schedule/{self.jid}", json={
            "shorts": [{"idx": i, "keep": True} for i in idxs], "schedule": schedule, "tz": "UTC", **extra})

    def posts(self):
        return {p["idx"]: p for p in F.job_json(self.jid).get("ig_posts") or []}

    def wait_status(self, idx, status):
        return F.wait(lambda: self.posts().get(idx, {}).get("status") == status and self.posts()[idx],
                      what=f"Reel {idx} {status}")

    def test_post_now(self):
        self.assertEqual(self.plan((1, 2)).status_code, 200)
        p = self.wait_status(1, "done")
        self.wait_status(2, "done")
        self.assertIn(p["media_id"], F.REELS)
        self.assertTrue(p["permalink"].startswith("https://www.instagram.com/reel/"))
        caption = F.REELS[p["media_id"]]["caption"]
        self.assertIn("#reels", caption)
        self.assertLessEqual(len(caption), 2200)
        url = next(iter(F.IG_CONTAINERS.values()))["video_url"]
        self.assertTrue(url.startswith("https://pitcrew.test/ig-video/"))
        self.assertEqual(self.plan((1,)).status_code, 400)  # already on Instagram

    def test_video_link(self):
        self.plan((1,))
        self.wait_status(1, "done")
        url = next(iter(F.IG_CONTAINERS.values()))["video_url"]
        path = urllib.parse.urlparse(url).path
        anyone = F.client()  # Instagram isn't signed in to Pit Crew
        r = anyone.get(path)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, "video/mp4")
        token = path.split("/")[-1][:-4]
        self.assertEqual(anyone.get(f"/ig-video/{token[:-2]}xx.mp4").status_code, 404)  # tampered
        self.assertEqual(anyone.get("/ig-video/nonsense.mp4").status_code, 404)

    def test_planned_for_later_waits(self):
        start = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        r = self.plan((1, 2), "custom", start=start, every=6)
        self.assertEqual(r.status_code, 200, r.json)
        time.sleep(0.3)
        posts = self.posts()
        self.assertEqual({p["status"] for p in posts.values()}, {"waiting"})
        t1, t2 = (datetime.fromisoformat(posts[i]["when"]) for i in (1, 2))
        self.assertEqual(t2 - t1, timedelta(hours=6))
        self.assertEqual(F.REELS, {})
        clips = {c["idx"]: c for c in self.c.get("/api/clips").json["items"]}
        self.assertEqual(clips[1]["status"], "scheduled")
        self.assertEqual(self.c.post(f"/api/instagram/cancel/{self.jid}/1").status_code, 200)
        self.assertNotIn(1, self.posts())

    def test_same_time_as_youtube(self):
        F.connect_youtube(self.u["id"])
        start = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M")
        self.c.post(f"/api/schedule/{self.jid}", json={"shorts": [{"idx": 1, "keep": True}], "schedule": "custom",
                                                       "start": start, "tz": "UTC"})
        F.wait(lambda: F.job_json(self.jid).get("upload_status") == "done", what="YouTube")
        r = self.plan((1,), "same")
        self.assertEqual(r.status_code, 200, r.json)
        yt_when = datetime.fromisoformat(F.job_json(self.jid)["uploads"][0]["when"])
        self.assertEqual(datetime.fromisoformat(self.posts()[1]["when"]), yt_when.astimezone(timezone.utc))

    def test_failure_then_try_again(self):
        from web.notices import WATCHING
        WATCHING.clear()  # nobody has the page open: the creator is emailed
        F.IG.fail_publish = "(#9) Application request limit reached"
        self.plan((1,))
        p = self.wait_status(1, "error")
        self.assertIn("limit", p["error"])
        F.wait_for_mail(self.u["email"], "Instagram")  # the creator is told by email
        self.assertEqual(self.c.post(f"/api/instagram/retry/{self.jid}/1").status_code, 200)
        self.wait_status(1, "done")
        self.assertEqual(self.c.post(f"/api/instagram/retry/{self.jid}/1").status_code, 400)

    def test_account_gone_before_posting_time(self):
        self.plan((1,), "custom", start=(datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"))
        db.drop_connection(db.connection(self.u["id"], "instagram")["id"])
        from web import instagram_posting as IPOST
        IPOST._edit(self.jid, 1, when=None)  # due now
        IPOST._WAKE.set()
        p = self.wait_status(1, "error")
        self.assertIn("isn't connected", p["error"])

    def test_personal_account_refused_when_planning(self):
        F.connect_instagram(self.u["id"], "777", "personal.one", account_type="PERSONAL")
        r = self.plan((1,), ig_id="777")
        self.assertEqual(r.status_code, 400)
        self.assertTrue(r.json["switch"])

    def test_interrupted_post_becomes_check(self):
        from web import instagram_posting as IPOST
        IPOST._mutate(self.jid, lambda ps: ps + [{"idx": 3, "status": "posting", "ig_id": "1789", "title": "x"}])
        IPOST._startup.__wrapped__ if hasattr(IPOST._startup, "__wrapped__") else None
        # what _startup does for a job.json that says "posting" after a restart
        from web.store import JOBS
        JOBS.pop(self.jid)
        import threading
        t = threading.Thread(target=IPOST._startup, daemon=True)
        t.start()
        p = self.wait_status(3, "check")
        self.assertIn("Check Instagram", p["error"])

    def test_scheduled_page_lists_reels(self):
        self.plan((1,))
        self.wait_status(1, "done")
        items = self.c.get("/api/instagram/posts").json["items"]
        self.assertEqual([(i["job"], i["idx"], i["status"]) for i in items], [(self.jid, 1, "done")])


if __name__ == "__main__":
    unittest.main()
