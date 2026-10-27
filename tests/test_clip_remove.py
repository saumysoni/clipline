"""Taking a posted clip down from Shorts & Reels (web/clip_remove.py): Pit Crew deletes the Short on YouTube; a Reel is
deleted by the creator in Instagram and Pit Crew only forgets it once Instagram says it's gone."""
from tests import fakes as F

import unittest

CH1 = "UCchannel000000000000001"


class Remove(unittest.TestCase):
    def setUp(self):
        F.install()
        F.reset()
        self.u = F.new_user()
        self.c = F.client(self.u)
        self.jid, self.st = F.make_shorts(self.c, 150, 3)

    def clip(self, idx=1):
        return next(c for c in self.c.get("/api/clips").json["items"] if c["job"] == self.jid and c["idx"] == idx)

    def test_delete_on_youtube(self):
        F.connect_youtube(self.u["id"], CH1)
        self.c.post(f"/api/schedule/{self.jid}", json={"shorts": [{"idx": 1, "keep": True}], "schedule": "now", "tz": "UTC", "channel": CH1})
        job = F.wait(lambda: F.job_json(self.jid).get("upload_status") == "done" and F.job_json(self.jid), what="posting")
        vid = job["uploads"][0]["video_id"]
        self.assertIn(vid, F.VIDEOS)
        r = self.c.post(f"/api/clips/{self.jid}/1/delete-youtube")
        self.assertEqual(r.status_code, 200, r.json)
        self.assertNotIn(vid, F.VIDEOS)
        self.assertEqual(F.job_json(self.jid).get("uploads"), [])
        self.assertEqual(self.clip()["status"], "draft")  # back to Drafts
        self.assertEqual(self.c.post(f"/api/clips/{self.jid}/1/delete-youtube").status_code, 400)  # nothing left

    def test_already_deleted_in_studio_is_just_forgotten(self):
        F.connect_youtube(self.u["id"], CH1)
        self.c.post(f"/api/schedule/{self.jid}", json={"shorts": [{"idx": 2, "keep": True}], "schedule": "now", "tz": "UTC", "channel": CH1})
        job = F.wait(lambda: F.job_json(self.jid).get("upload_status") == "done" and F.job_json(self.jid), what="posting")
        F.VIDEOS.pop(job["uploads"][0]["video_id"])
        self.assertEqual(self.c.post(f"/api/clips/{self.jid}/2/delete-youtube").status_code, 200)
        self.assertEqual(self.clip(2)["status"], "draft")

    def test_someone_else_cant(self):
        other = F.client(F.new_user())
        self.assertIn(other.post(f"/api/clips/{self.jid}/1/delete-youtube").status_code, (403, 404))

    def test_instagram_forgotten_only_once_gone(self):
        F.connect_instagram(self.u["id"])
        self.c.post(f"/api/instagram/schedule/{self.jid}", json={"shorts": [{"idx": 1, "keep": True}], "schedule": "now", "tz": "UTC"})
        p = F.wait(lambda: next((p for p in F.job_json(self.jid).get("ig_posts") or [] if p["status"] == "done"), None), what="the Reel")
        r = self.c.post(f"/api/clips/{self.jid}/1/instagram-gone")
        self.assertEqual(r.status_code, 200, r.json)
        self.assertFalse(r.json["gone"])  # still on Instagram: kept
        self.assertTrue(F.job_json(self.jid)["ig_posts"])
        F.IG.deleted_reels.add(p["media_id"])  # the creator deletes it in the app
        r = self.c.post(f"/api/clips/{self.jid}/1/instagram-gone")
        self.assertTrue(r.json["gone"])
        self.assertEqual(F.job_json(self.jid)["ig_posts"], [])
        self.assertEqual(self.clip()["status"], "draft")


if __name__ == "__main__":
    unittest.main()
