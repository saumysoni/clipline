"""Editing made Shorts: hooks, Try again, Add a Short, thumbnail look, post text, Choose on the video, titles,
deleting drafts, the Vlogs and Shorts & Reels lists (web/hooks.py, web/try_again.py, web/add_short.py,
web/thumbnail_look.py, web/post_text.py, web/preview.py, web/clips.py, web/vlogs.py)."""
from tests import fakes as F

import unittest

from settings import JOBS_DIR


class Base(unittest.TestCase):
    seconds, count = 150, 3

    def setUp(self):
        F.install()
        F.reset()
        self.u = F.new_user()
        self.c = F.client(self.u)
        self.jid, self.st = F.make_shorts(self.c, self.seconds, self.count)

    def short(self, idx):
        return next((s for s in F.job_json(self.jid)["shorts"] if s["idx"] == idx), None)

    def settled(self, idx):
        return F.wait(lambda: (s := self.short(idx)) and not s.get("retrying") and not s.get("pending") and s,
                      what=f"Short {idx} to settle")


class Hooks(Base):
    def test_new_hook_ideas_and_set_one(self):
        r = self.c.post(f"/api/hooks/{self.jid}/1", json={"note": "funnier"})
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual(r.json["pick"], "bold")
        self.assertIn("bold", r.json["hooks"])
        r = self.c.post(f"/api/hook/{self.jid}/1", json={"text": "  Wait   for it  ", "style": "custom"})
        self.assertEqual(r.status_code, 200)
        s = self.settled(1)
        self.assertEqual(s["hook"], "Wait for it")
        self.assertEqual(s["hook_mode"], "text")
        ass = (JOBS_DIR / self.jid / f"captions_{s['video'].split('_')[1].split('.')[0]}.ass").read_text()
        self.assertIn("Wait for it", ass)

    def test_no_text_hook_and_empty(self):
        self.assertEqual(self.c.post(f"/api/hook/{self.jid}/2", json={"text": ""}).status_code, 400)
        self.c.post(f"/api/hook/{self.jid}/2", json={"mode": "none"})
        self.assertEqual(self.settled(2)["hook_mode"], "none")

    def test_busy_short_refuses_a_second_change(self):
        from web.store import update_short
        update_short(self.jid, 3, retrying=True)
        r = self.c.post(f"/api/hook/{self.jid}/3", json={"text": "Hey"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.c.post(f"/api/retry/{self.jid}/3", json={}).status_code, 400)
        update_short(self.jid, 3, retrying=False)


class NoRoom(Base):
    def test_try_again_when_every_moment_is_taken_says_so(self):
        before = self.short(1)
        self.c.post(f"/api/retry/{self.jid}/1", json={})
        after = self.settled(1)
        self.assertIn("Choose on the video", after["retry_error"])
        self.assertEqual((after["start"], after["video"]), (before["start"], before["video"]))  # the Short is kept


class TryAgainAndAdd(Base):
    seconds = 300  # room for another moment next to the three Shorts
    def test_try_again_picks_another_moment(self):
        before = self.short(1)
        self.assertEqual(self.c.post(f"/api/retry/{self.jid}/1", json={"note": "the market part"}).status_code, 200)
        after = self.settled(1)
        self.assertFalse(after.get("retry_error"), after.get("retry_error"))
        self.assertNotEqual((after["start"], after["end"]), (before["start"], before["end"]))
        self.assertEqual(after["tried"][-1]["start"], before["start"])
        self.assertNotEqual(after["video"], before["video"])  # a new file: the old one may be on YouTube
        self.assertIn("again", F.AI.kinds())

    def test_try_again_with_own_times(self):
        self.c.post(f"/api/retry/{self.jid}/2", json={"start": "0:40", "end": "1:05"})
        s = self.settled(2)
        self.assertAlmostEqual(s["start"], 40, delta=1)
        self.assertAlmostEqual(s["end"], 65, delta=1)
        self.assertEqual(self.c.post(f"/api/retry/{self.jid}/2", json={"start": "1:05", "end": "0:40"}).status_code, 400)

    def test_add_a_short(self):
        self.assertEqual(self.c.post(f"/api/add/{self.jid}", json={}).status_code, 400)
        r = self.c.post(f"/api/add/{self.jid}", json={"start": "2:00", "end": "2:20"})
        self.assertEqual(r.status_code, 200)
        idx = r.json["idx"]
        s = self.settled(idx)
        self.assertAlmostEqual(s["start"], 120, delta=1)
        self.assertEqual(len(F.job_json(self.jid)["shorts"]), 4)

    def test_video_gone_explains(self):
        self.c.post(f"/api/vlogs/{self.jid}/delete-video")
        r = self.c.post(f"/api/retry/{self.jid}/1", json={})
        if r.status_code == 200:
            self.assertIn("deleted", self.settled(1)["retry_error"])
        else:
            self.assertIn("deleted", r.json["error"])


class Look(Base):
    def test_simple_thumbnail_cant_change_look(self):
        self.assertEqual(self.c.post(f"/api/look/{self.jid}/1", json={"look": "neon"}).status_code, 400)
        self.c.post(f"/api/look/{self.jid}/1", json={"look": "duotone"})
        self.assertIn("simple style", self.settled(1)["retry_error"])


class PostText(Base):
    def test_caption_and_hashtags(self):
        r = self.c.get(f"/api/clips/{self.jid}/1/post-text").json
        self.assertEqual(r["caption"], "")
        self.assertTrue(r["suggested"])
        r = self.c.post(f"/api/clips/{self.jid}/1/post-text", json={"caption": "My caption", "hashtags": ["#Road Trip", "food"]})
        self.assertEqual(r.status_code, 200, r.json)
        s = self.short(1)
        self.assertEqual(s["ig_caption"], "My caption")
        self.assertIn("food", s["hashtags"])
        too_long = self.c.post(f"/api/clips/{self.jid}/1/post-text", json={"caption": "x" * 2300})
        self.assertEqual(too_long.status_code, 400)
        too_many = self.c.post(f"/api/clips/{self.jid}/1/post-text", json={"hashtags": [f"t{i}" for i in range(40)]})
        self.assertEqual(too_many.status_code, 400)

    def test_ai_ideas(self):
        for kind in ("title", "caption"):
            r = self.c.post(f"/api/clips/{self.jid}/1/suggest", json={"kind": kind})
            self.assertEqual(r.status_code, 200, r.json)
            self.assertEqual(len(r.json["items"]), 3)
        self.assertEqual(self.c.get(f"/api/clips/{self.jid}/99/post-text").status_code, 404)


class ChooseOnVideo(Base):
    def test_plays_the_original_when_browsers_can(self):
        r = self.c.post(f"/api/preview/{self.jid}", json={}).json
        self.assertEqual(r["status"], "source")
        self.assertTrue(self.c.get(r["url"]).status_code == 200)


class Lists(Base):
    def test_vlogs_and_clips(self):
        v = self.c.get("/api/vlogs").json["items"]
        self.assertEqual([x["id"] for x in v], [self.jid])
        clips = self.c.get("/api/clips").json["items"]
        self.assertEqual({c["status"] for c in clips}, {"draft"})
        self.assertTrue(all(c["expires"] for c in clips))  # drafts are deleted after KEEP_DRAFT_DAYS
        self.assertEqual(self.c.post(f"/api/clips/{self.jid}/1/title", json={"title": " New name "}).status_code, 200)
        self.assertEqual(self.short(1)["title"], "New name")
        self.assertEqual(self.c.post(f"/api/clips/{self.jid}/1/title", json={"title": " "}).status_code, 400)

    def test_delete_drafts_only(self):
        F.connect_youtube(self.u["id"])
        self.c.post(f"/api/schedule/{self.jid}", json={"shorts": [{"idx": 1, "keep": True}], "schedule": "now"})
        F.wait(lambda: F.job_json(self.jid).get("upload_status") == "done", what="posted")
        r = self.c.post("/api/clips/delete", json={"items": [{"job": self.jid, "idx": 1}, {"job": self.jid, "idx": 2}]})
        self.assertEqual(r.json["deleted"], [{"job": self.jid, "idx": 2}])
        self.assertEqual([k["idx"] for k in r.json["kept"]], [1])
        self.assertFalse((JOBS_DIR / self.jid / self.st["shorts"][1]["video"]).exists())
        r = self.c.post("/api/clips/delete", json={"items": [{"job": self.jid, "idx": 1}]})
        self.assertEqual(r.status_code, 400)

    def test_schedule_several_clips_on_both(self):
        F.connect_youtube(self.u["id"])
        F.connect_instagram(self.u["id"])
        items = [{"job": self.jid, "idx": i} for i in (1, 2)]
        r = self.c.post("/api/clips/schedule", json={"items": items, "youtube": True, "instagram": True,
                                                     "schedule": "now", "tz": "UTC"})
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual((r.json["youtube"], r.json["instagram"]), (2, 2))
        F.wait(lambda: len(F.job_json(self.jid).get("uploads") or []) == 2, what="YouTube")
        F.wait(lambda: all(p["status"] == "done" for p in F.job_json(self.jid)["ig_posts"]), what="Instagram")
        clips = {c["idx"]: c["status"] for c in self.c.get("/api/clips").json["items"]}
        self.assertEqual((clips[1], clips[2], clips[3]), ("posted", "posted", "draft"))
        r = self.c.post("/api/clips/schedule", json={"items": items, "youtube": True, "schedule": "now"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.c.post("/api/clips/schedule", json={"items": items}).status_code, 400)

    def test_delete_vlog_videos(self):
        r = self.c.post("/api/vlogs/delete-videos", json={"ids": [self.jid, "not-an-id", "0000000000"]})
        self.assertEqual(r.json["deleted"], [self.jid])
        self.assertFalse(list((JOBS_DIR / self.jid).glob("source.*")))
        self.assertTrue(F.job_json(self.jid)["video_deleted_at"])
        self.assertEqual(len(self.c.get("/api/clips").json["items"]), 3)  # the Shorts stay
        r = self.c.post("/api/vlogs/delete-videos", json={"ids": [self.jid]})
        self.assertEqual(r.json["skipped"], [self.jid])


if __name__ == "__main__":
    unittest.main()
