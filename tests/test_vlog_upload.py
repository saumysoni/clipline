"""Uploading a whole vlog to YouTube: prepare (title ideas, description with chapters, tags, thumbnail), edit,
upload public / scheduled, then Shorts from the same video (web/vlog_upload.py, pipeline/vlog_meta.py)."""
from tests import fakes as F

import unittest
from datetime import datetime, timedelta

CH = "UCchannel000000000000001"


class VlogUpload(unittest.TestCase):
    def setUp(self):
        F.install()
        F.reset()
        self.u = F.new_user()
        self.c = F.client(self.u)
        up = F.upload(self.c, F.test_video(150))
        r = self.c.post("/api/vlog/start", data={"upload": up, "note": "a hill trip"})
        self.assertEqual(r.status_code, 200, r.json)
        self.jid = r.json["id"]
        self.st = F.wait_ready(self.c, self.jid)

    def test_prepared_details(self):
        self.assertEqual(self.st["status"], "ready", self.st)
        d = self.st["vdraft"]
        self.assertEqual(d["title"], "A day in the hills")
        self.assertEqual(len(d["titles"]), 3)
        self.assertIn("0:00", d["description"])  # chapters are written into the description
        self.assertTrue(d["tags"])
        self.assertTrue(d["thumb"])
        self.assertEqual(self.c.get("/api/vlogs").json["items"][0]["prep"], True)

    def test_ai_down_means_the_creator_writes_them(self):
        F.AI.fail(503, "overloaded", times=200)
        up = F.upload(self.c, F.test_video(60))
        jid = self.c.post("/api/vlog/start", data={"upload": up}).json["id"]
        st = F.wait_ready(self.c, jid, timeout=120)
        self.assertEqual(st["status"], "ready")
        self.assertTrue(st["vdraft"]["ai_failed"])

    def test_draft_saved_as_typed_and_tags_cleaned(self):
        r = self.c.post(f"/api/vlog/{self.jid}/draft", json={"title": "  My   title ", "description": "Hi",
                                                            "tags": "Hills, hills, #road trip,  , food"})
        self.assertEqual(r.status_code, 200)
        d = F.job_json(self.jid)["vdraft"]
        self.assertEqual(d["title"], "My title")
        self.assertEqual(d["description"], "Hi")
        self.assertEqual(len(d["tags"]), len({t.lower() for t in d["tags"]}))  # no duplicates
        self.assertNotIn("", d["tags"])

    def test_upload_public_then_refuse_twice(self):
        self.assertTrue(self.c.post(f"/api/vlog/{self.jid}/upload", json={"title": "x"}).json.get("signin"))
        F.connect_youtube(self.u["id"], CH, handle="@hills")
        r = self.c.post(f"/api/vlog/{self.jid}/upload", json={"privacy": "public", "channel": CH})
        self.assertEqual(r.status_code, 200, r.json)
        post = F.wait(lambda: F.job_json(self.jid)["vpost"]["state"] == "done" and F.job_json(self.jid)["vpost"], what="sent")
        v = F.VIDEOS[post["video_id"]]
        self.assertEqual(v["kind"], "videoOnDemand")
        self.assertEqual(v["privacy"], "public")
        self.assertEqual(F.job_json(self.jid)["vlog"]["channel_handle"], "@hills")
        self.assertIn("already on YouTube", self.c.post(f"/api/vlog/{self.jid}/upload", json={}).json["error"])

    def test_schedule_and_bad_time(self):
        F.connect_youtube(self.u["id"], CH)
        r = self.c.post(f"/api/vlog/{self.jid}/upload", json={"privacy": "schedule", "start": "2020-01-01T10:00"})
        self.assertEqual(r.json["field"], "start")
        start = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
        self.c.post(f"/api/vlog/{self.jid}/upload", json={"privacy": "schedule", "start": start, "tz": "UTC"})
        post = F.wait(lambda: F.job_json(self.jid)["vpost"]["state"] == "done" and F.job_json(self.jid)["vpost"], what="sent")
        self.assertEqual(F.VIDEOS[post["video_id"]]["publish_at"].strftime("%Y-%m-%dT%H:%M"), start)
        vl = self.c.get("/api/vlogs").json["items"][0]
        self.assertEqual(vl["vpost"]["state"], "done")

    def test_shorts_from_the_same_video_link_back(self):
        F.connect_youtube(self.u["id"], CH, handle="@hills")
        self.c.post(f"/api/vlog/{self.jid}/upload", json={"privacy": "public"})
        post = F.wait(lambda: F.job_json(self.jid)["vpost"]["state"] == "done" and F.job_json(self.jid)["vpost"], what="sent")
        ai_before = len(F.AI.calls)
        r = self.c.post(f"/api/vlog/{self.jid}/shorts", json={"count": 2, "style": "clean"})
        self.assertEqual(r.status_code, 200, r.json)
        st = F.wait_ready(self.c, self.jid)
        self.assertEqual(st["status"], "ready")
        self.assertEqual(len(st["shorts"]), 2)
        self.assertEqual(st["style"], "clean")
        self.assertEqual(F.AI.kinds()[ai_before:].count("meta"), 0)  # the details aren't written again
        self.c.post(f"/api/schedule/{self.jid}", json={"shorts": [{"idx": 1, "keep": True}], "schedule": "now"})
        F.wait(lambda: F.job_json(self.jid).get("upload_status") == "done", what="Short posted")
        short = F.VIDEOS[F.job_json(self.jid)["uploads"][0]["video_id"]]
        self.assertIn(f"https://www.youtube.com/watch?v={post['video_id']}", short["desc"])
        self.assertIn("This vlog already has Shorts", self.c.post(f"/api/vlog/{self.jid}/shorts", json={}).json["error"])

    def test_vlog_removed_by_youtube_shows_as_removed(self):
        F.connect_youtube(self.u["id"], CH)
        self.c.post(f"/api/vlog/{self.jid}/upload", json={"privacy": "public"})
        post = F.wait(lambda: F.job_json(self.jid)["vpost"]["state"] == "done" and F.job_json(self.jid)["vpost"], what="sent")
        F.VIDEOS.pop(post["video_id"])
        import web.youtube_sync as YS
        YS._LAST.clear()
        YS.FRESH = 0
        YS.sync_deleted(self.u["id"], force=True)
        self.assertEqual(F.job_json(self.jid)["vpost"]["state"], "removed")
        YS.FRESH = 120


if __name__ == "__main__":
    unittest.main()
