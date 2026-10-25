"""Posting to YouTube: schedule, post now, the channel the page showed, reschedule, edit after posting, unmark, the
posted list, keeping in step with Studio, several channels (web/posting.py, web/on_youtube.py, web/youtube_sync.py,
web/youtube_connect.py)."""
from tests import fakes as F

import unittest
from datetime import datetime, timedelta, timezone

from accounts import db

CH1, CH2 = "UCchannel000000000000001", "UCchannel000000000000002"


class Base(unittest.TestCase):
    def setUp(self):
        F.install()
        F.reset()
        self.u = F.new_user()
        self.c = F.client(self.u)
        self.jid, self.st = F.make_shorts(self.c, 150, 3)

    def post(self, schedule="now", shorts=None, **extra):
        rows = shorts or [{"idx": s["idx"], "keep": True} for s in self.st["shorts"]]
        return self.c.post(f"/api/schedule/{self.jid}", json={"shorts": rows, "schedule": schedule, "tz": "UTC", **extra})

    def done(self):
        return F.wait(lambda: F.job_json(self.jid).get("upload_status") in ("done", "error") and F.job_json(self.jid),
                      what="posting to finish")


class Schedule(Base):
    def test_needs_a_channel(self):
        r = self.post()
        self.assertEqual(r.status_code, 400)
        self.assertTrue(r.json["signin"])

    def test_post_now_with_descriptions(self):
        F.connect_youtube(self.u["id"], CH1, handle="@hills")
        self.assertEqual(self.post(channel=CH1).status_code, 200)
        job = self.done()
        self.assertEqual(job["upload_status"], "done")
        self.assertEqual(len(job["uploads"]), 3)
        for u in job["uploads"]:
            self.assertIsNone(u["when"])
            self.assertEqual(u["channel"], CH1)
            self.assertIn("uploaded_at", u)
            v = F.VIDEOS[u["video_id"]]
            self.assertTrue(v["title"].endswith("#Shorts"))
            self.assertIn("More from @hills", v["desc"])
            self.assertIn("#Shorts", v["desc"])
        again = self.post(channel=CH1)
        self.assertEqual(again.status_code, 400)
        self.assertIn("already on YouTube", again.json["error"])

    def test_scheduled_times_and_title_edit(self):
        F.connect_youtube(self.u["id"], CH1)
        start = (datetime.now() + timedelta(days=2)).replace(second=0, microsecond=0)
        rows = [{"idx": 1, "keep": True, "title": "  My own title  "}, {"idx": 2, "keep": True}, {"idx": 3, "keep": False}]
        r = self.post("custom", rows, start=start.strftime("%Y-%m-%dT%H:%M"), every=12)
        self.assertEqual(r.status_code, 200, r.json)
        ups = sorted(self.done()["uploads"], key=lambda u: u["idx"])
        self.assertEqual([u["idx"] for u in ups], [1, 2])
        t1, t2 = (datetime.fromisoformat(u["when"]) for u in ups)
        self.assertEqual(t2 - t1, timedelta(hours=12))
        self.assertEqual(ups[0]["title"], "My own title")
        self.assertEqual(F.VIDEOS[ups[0]["video_id"]]["privacy"], "private")

    def test_bad_time_and_nothing_ticked(self):
        F.connect_youtube(self.u["id"], CH1)
        r = self.post("custom", start="2020-01-01T10:00")
        self.assertEqual(r.json["field"], "start")
        r = self.post(shorts=[{"idx": 1, "keep": False}])
        self.assertIn("Tick at least one", r.json["error"])

    def test_channel_the_page_showed_not_the_active_one(self):
        F.connect_youtube(self.u["id"], CH1)
        F.connect_youtube(self.u["id"], CH2, title="Second")  # now the active one
        self.post(channel=CH1)
        self.assertEqual({u["channel"] for u in self.done()["uploads"]}, {CH1})
        r = self.post(channel="UCnotconnected00000000001")
        self.assertEqual(r.status_code, 400)

    def test_upload_failure_keeps_what_went_up(self):
        F.connect_youtube(self.u["id"], CH1)
        real = __import__("youtube").upload_short
        calls = []

        def flaky(*a, **k):
            calls.append(1)
            if len(calls) == 2:
                raise RuntimeError("uploadLimitExceeded")
            return real(*a, **k)
        __import__("youtube").upload_short = flaky
        try:
            self.post()
            job = self.done()
        finally:
            __import__("youtube").upload_short = real
        self.assertEqual(job["upload_status"], "error")
        self.assertEqual(len(job["uploads"]), 1)
        self.assertIn("1 already on YouTube", job["upload_msg"])
        self.post()  # pressing again posts only the rest
        self.assertEqual(len(self.done()["uploads"]), 3)


class AfterPosting(Base):
    def setUp(self):
        super().setUp()
        F.connect_youtube(self.u["id"], CH1)
        start = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
        self.post("custom", start=start)
        self.ups = {u["idx"]: u for u in self.done()["uploads"]}

    def test_reschedule(self):
        new = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M")
        r = self.c.post(f"/api/reschedule/{self.jid}/1", json={"start": new, "tz": "UTC"})
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual(F.VIDEOS[self.ups[1]["video_id"]]["publish_at"].strftime("%Y-%m-%dT%H:%M"), new)
        self.assertEqual(F.job_json(self.jid)["uploads"][0]["when"][:16], new)

    def test_title_only_edit_and_nothing_changed(self):
        r = self.c.post(f"/api/repost/{self.jid}/1", json={"title": self.ups[1]["title"]})
        self.assertIn("Nothing has changed", r.json["error"])
        r = self.c.post(f"/api/repost/{self.jid}/1", json={"title": "Better title"})
        self.assertEqual(r.json["done"], "title")
        self.assertEqual(F.VIDEOS[self.ups[1]["video_id"]]["title"], "Better title #Shorts")

    def test_replace_an_edited_short(self):
        from web.store import update_short
        update_short(self.jid, 2, video="short_2_v2.mp4")
        F.copy_into(self.jid, F.TMP / "jobs" / self.jid / "short_2.mp4", "short_2_v2.mp4")
        old = self.ups[2]["video_id"]
        r = self.c.post(f"/api/repost/{self.jid}/2", json={})
        self.assertEqual(r.json["done"], "replace")
        job = self.done()
        new = next(u for u in job["uploads"] if u["idx"] == 2)
        self.assertNotEqual(new["video_id"], old)
        self.assertNotIn(old, F.VIDEOS)  # the old version was deleted after the new one went up
        self.assertEqual(new["when"], self.ups[2]["when"])  # same time

    def test_never_replace_a_public_short(self):
        from web.store import update_short
        F.VIDEOS[self.ups[3]["video_id"]]["publish_at"] = datetime.now(timezone.utc) - timedelta(hours=1)
        update_short(self.jid, 3, video="short_3_v2.mp4")
        r = self.c.post(f"/api/repost/{self.jid}/3", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("already public", r.json["error"])

    def test_deleted_in_studio_becomes_a_draft_again(self):
        F.VIDEOS.pop(self.ups[1]["video_id"])
        items = self.c.get("/api/posted").json["items"]
        self.assertEqual(sorted(i["idx"] for i in items), [2, 3])
        clips = {c["idx"]: c["status"] for c in self.c.get("/api/clips").json["items"]}
        self.assertEqual(clips[1], "draft")
        r = self.c.post(f"/api/reschedule/{self.jid}/1", json={"start": "2030-01-01T10:00", "tz": "UTC"})
        self.assertEqual(r.status_code, 404)

    def test_unmark(self):
        self.assertEqual(self.c.post(f"/api/unmark/{self.jid}/2").status_code, 200)
        self.assertEqual(sorted(u["idx"] for u in F.job_json(self.jid)["uploads"]), [1, 3])

    def test_posted_list_states(self):
        items = self.c.get("/api/posted").json
        self.assertTrue(items["live"])
        self.assertTrue(all(i["state"]["privacy"] == "private" for i in items["items"]))
        db.drop_connection(db.connection(self.u["id"], "youtube", CH1)["id"])
        F.connect_youtube(self.u["id"], CH2)
        items = self.c.get("/api/posted").json["items"]
        self.assertTrue(all(i["state"]["privacy"] == "other_channel" for i in items))


class Channels(unittest.TestCase):
    def setUp(self):
        F.install()
        F.reset()
        self.u = F.new_user()
        self.c = F.client(self.u)

    def test_switch_and_disconnect(self):
        F.connect_youtube(self.u["id"], CH1)
        F.connect_youtube(self.u["id"], CH2)
        self.assertEqual(db.connection(self.u["id"], "youtube")["account_id"], CH2)
        self.assertEqual(self.c.post("/api/youtube/switch", json={"channel": CH1}).status_code, 200)
        self.assertEqual(db.connection(self.u["id"], "youtube")["account_id"], CH1)
        self.assertEqual(self.c.post("/api/youtube/switch", json={"channel": "UCnope"}).status_code, 400)
        self.c.post("/api/youtube/signout", json={"channel": CH1})
        self.assertEqual(db.connection(self.u["id"], "youtube")["account_id"], CH2)  # the other one is active now
        self.assertIn(CH1, F.REVOKED)

    def test_connect_page_redirects_to_google_with_state(self):
        import youtube
        real = youtube.start_google
        youtube.start_google = lambda purpose, redirect, nxt, popup: (
            f"https://accounts.google.com/o/oauth2/auth?redirect_uri={redirect}", {"purpose": purpose, "state": "s"})
        try:
            r = self.c.get("/api/youtube/signin?popup=1")
        finally:
            youtube.start_google = real
        self.assertEqual(r.status_code, 302)
        self.assertIn("accounts.google.com", r.headers["Location"])
        self.assertIn("/api/youtube/callback", r.headers["Location"])
        with self.c.session_transaction() as s:
            self.assertEqual(s["google"]["purpose"], "youtube")

    def test_callback_without_a_started_sign_in_does_nothing(self):
        r = self.c.get("/api/youtube/callback?code=x&state=forged")
        self.assertIn(r.status_code, (200, 302, 400))
        self.assertEqual(db.connections(self.u["id"], "youtube"), [])


if __name__ == "__main__":
    unittest.main()
