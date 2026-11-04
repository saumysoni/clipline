"""The channel's other videos on the Videos page and Shorts & Reels (web/channel_videos.py), and "Removed or deleted" cards
for anything gone from YouTube or Instagram (web/youtube_sync.py, web/removed.py), checked once a day."""
from tests import _env  # noqa: F401  (first: clean settings)

import time
import unittest
from unittest import mock

from tests import fakes as F
from accounts import db
from instagram.http import InstagramError
from settings import JOBS_DIR
from youtube.channel_videos import is_short, seconds_of
import web.channel_videos as CV
import web.removed as RM
import web.youtube_sync as YS
import web.youtube_upkeep as UP

CH = "UCchannel000000000000001"


class Classifier(unittest.TestCase):
    def test_short_by_tag_or_length(self):
        self.assertTrue(is_short("Big day #Shorts", "", [], 900))
        self.assertTrue(is_short("Big day", "see #short", [], 900))
        self.assertTrue(is_short("Big day", "", ["shorts"], 900))
        self.assertTrue(is_short("Big day", "", ["#Short"], 900))
        self.assertTrue(is_short("Quick one", "", [], 180))
        self.assertFalse(is_short("Long one", "", [], 181))
        self.assertFalse(is_short("Shortstop tips #shortstop", "", ["short film"], 900))
        self.assertFalse(is_short("A live stream", "", [], 0))

    def test_durations(self):
        self.assertEqual(seconds_of("PT1H2M3S"), 3723)
        self.assertEqual(seconds_of("P1D"), 86400)
        self.assertEqual(seconds_of("nonsense"), 0)


class Base(unittest.TestCase):
    def setUp(self):
        F.install()
        F.reset()
        CV._RUNNING.clear()
        CV._ASKED.clear()
        self.u = F.new_user()
        self.c = F.client(self.u)
        F.connect_youtube(self.u["id"])

    def outside(self, vid, title, **kw):
        F.VIDEOS[vid] = {"title": title, "channel": CH, "privacy": "public", **kw}


class ChannelVideos(Base):
    def test_long_and_short_are_listed_with_links_and_private_is_not(self):
        self.outside("longvideo01", "Road trip", seconds=900)
        self.outside("shortvid001", "Quick #shorts", seconds=40)
        self.outside("privatevid1", "Secret", seconds=900, privacy="private")
        CV.refresh_user(self.u["id"])
        items = {i["id"]: i for i in self.c.get("/api/channel-videos").json["items"]}
        self.assertEqual(set(items), {"longvideo01", "shortvid001"})
        self.assertFalse(items["longvideo01"]["short"])
        self.assertEqual(items["longvideo01"]["url"], "https://www.youtube.com/watch?v=longvideo01")
        self.assertTrue(items["shortvid001"]["short"])
        self.assertEqual(items["shortvid001"]["url"], "https://www.youtube.com/shorts/shortvid001")

    def test_what_pit_crew_posted_is_not_listed_twice(self):
        jid, st = F.make_shorts(self.c, count=1)
        self.c.post(f"/api/schedule/{jid}", json={"shorts": [{"idx": 1, "title": "One", "keep": True}], "schedule": "now"})
        F.wait(lambda: F.job_json(jid).get("uploads"), what="uploaded")
        CV.refresh_user(self.u["id"])
        self.assertEqual(self.c.get("/api/channel-videos").json["items"], [])

    def test_opening_the_page_reads_youtube_only_when_a_day_old(self):
        self.outside("longvideo01", "Road trip", seconds=900)
        CV.refresh_user(self.u["id"])
        with mock.patch.object(CV, "_soon") as soon:
            self.c.get("/api/channel-videos")
            soon.assert_not_called()
            db.set_channel_checked(self.u["id"], CH, time.time() - CV.DAY - 1)
            self.c.get("/api/channel-videos")
            soon.assert_called_once()

    def test_check_now_is_limited(self):
        with mock.patch.object(CV, "_soon") as soon:
            self.c.post("/api/channel-videos/check")
            self.c.post("/api/channel-videos/check")
            self.assertEqual(soon.call_count, 1)

    def test_gone_from_youtube_is_a_card_then_forgotten_and_a_youtube_error_changes_nothing(self):
        self.outside("longvideo01", "Road trip", seconds=900)
        CV.refresh_user(self.u["id"])
        F.VIDEOS.pop("longvideo01")
        with mock.patch("youtube.channel_videos", side_effect=RuntimeError("offline")):
            CV.refresh_user(self.u["id"])
        self.assertFalse(self.c.get("/api/channel-videos").json["items"][0]["gone"])
        CV.refresh_user(self.u["id"])
        item = self.c.get("/api/channel-videos").json["items"][0]
        self.assertTrue(item["gone"])
        self.assertEqual((item["url"], item["thumb"]), ("", ""))  # only the title is kept
        CV.refresh_user(self.u["id"], now=time.time() + 31 * CV.DAY)
        self.assertEqual(self.c.get("/api/channel-videos").json["items"], [])

    def test_gone_card_can_be_cleared(self):
        self.outside("longvideo01", "Road trip", seconds=900)
        self.outside("stillhere01", "Other", seconds=900)
        CV.refresh_user(self.u["id"])
        F.VIDEOS.pop("longvideo01")
        CV.refresh_user(self.u["id"])
        self.c.post("/api/channel-videos/longvideo01/remove")
        self.c.post("/api/channel-videos/stillhere01/remove")  # only a gone one can be cleared
        self.assertEqual([i["id"] for i in self.c.get("/api/channel-videos").json["items"]], ["stillhere01"])

    def test_gone_private_older_than_the_list_stay_accurate(self):
        """Not on the list isn't proof: YouTube's answer decides."""
        self.outside("longvideo01", "Road trip", seconds=900)
        CV.refresh_user(self.u["id"])
        F.VIDEOS["longvideo01"]["hidden_from_list"] = True
        with mock.patch("youtube.channel_videos", return_value=[]):
            CV.refresh_user(self.u["id"])  # past the end of the list, still on YouTube
        self.assertFalse(self.c.get("/api/channel-videos").json["items"][0]["gone"])

    def test_disconnected_channel_is_forgotten_and_delete_account_too(self):
        self.outside("longvideo01", "Road trip", seconds=900)
        CV.refresh_user(self.u["id"])
        UP.forget_channel(self.u["id"], CH)
        self.assertEqual(db.channel_video_rows(self.u["id"]), [])
        CV.refresh_user(self.u["id"])
        db.delete_user(self.u["id"])
        self.assertEqual(db.channel_video_rows(self.u["id"]), [])

    def test_one_creator_never_sees_anothers(self):
        self.outside("longvideo01", "Road trip", seconds=900)
        CV.refresh_user(self.u["id"])
        other = F.client(F.new_user())
        self.assertEqual(other.get("/api/channel-videos").json["items"], [])


class RemovedCards(Base):
    def posted(self, count=2):
        jid, _ = F.make_shorts(self.c, count=count)
        rows = [{"idx": i, "title": f"S{i}", "keep": i == 1} for i in range(1, count + 1)]
        self.c.post(f"/api/schedule/{jid}", json={"shorts": rows, "schedule": "now"})
        F.wait(lambda: F.job_json(jid).get("uploads") and F.job_json(jid).get("upload_status") == "done", what="posted")
        return jid

    def clip(self, jid, idx=1):
        return next(c for c in self.c.get("/api/clips").json["items"] if c["job"] == jid and c["idx"] == idx)

    def gone_from_youtube(self, jid):
        F.VIDEOS.pop(F.job_json(jid)["uploads"][0]["video_id"])
        YS.sync_deleted(self.u["id"], force=True)

    def test_pages_dont_ask_youtube(self):
        jid = self.posted()
        F.VIDEOS.pop(F.job_json(jid)["uploads"][0]["video_id"])
        self.assertEqual(self.clip(jid)["status"], "posted")  # until the daily check
        self.c.get("/api/vlogs")
        self.assertEqual(self.clip(jid)["status"], "posted")

    def test_short_gone_from_youtube_stops_counting_as_posted(self):
        jid = self.posted()
        self.gone_from_youtube(jid)
        c = self.clip(jid)
        self.assertEqual(c["status"], "removed")
        self.assertEqual(c["youtube"]["state"], "removed")
        self.assertIsNone(c["expires"])
        v = next(x for x in self.c.get("/api/vlogs").json["items"] if x["id"] == jid)
        self.assertEqual((v["posted"], v["removed"], v["drafts"]), (0, 1, 1))

    def test_back_to_drafts(self):
        jid = self.posted()
        self.gone_from_youtube(jid)
        self.assertTrue(self.c.post(f"/api/clips/{jid}/1/removed", json={"action": "draft"}).json["ok"])
        self.assertEqual(self.clip(jid)["status"], "draft")

    def test_remove_deletes_the_short(self):
        jid = self.posted()
        video = self.clip(jid)["video"]
        self.gone_from_youtube(jid)
        self.assertTrue(self.c.post(f"/api/clips/{jid}/1/removed", json={"action": "clear"}).json["ok"])
        self.assertEqual([c["idx"] for c in self.c.get("/api/clips").json["items"] if c["job"] == jid], [2])
        self.assertFalse((JOBS_DIR / jid / video).exists())

    def test_back_to_drafts_refused_once_the_file_has_gone(self):
        jid = self.posted()
        self.gone_from_youtube(jid)
        from web.store import update_short
        update_short(jid, 1, file_deleted_at=time.time())
        r = self.c.post(f"/api/clips/{jid}/1/removed", json={"action": "draft"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("no longer keeps", r.json["error"])

    def test_storage_timer_keeps_a_grey_card_then_deletes_it(self):
        """Posted long ago, last edited long ago: the draft timer mustn't take it the moment it's found gone."""
        from web import retention
        from web.store import JOBS, LOCK
        jid = self.posted()
        with LOCK:
            for s in JOBS[jid]["shorts"]:
                s["edited_at"] = time.time() - 40 * UP.DAY
        self.gone_from_youtube(jid)
        job = F.job_json(jid)
        s = next(x for x in job["shorts"] if x["idx"] == 1)
        self.assertFalse(retention.is_draft(job, s))
        self.assertIsNone(retention.draft_expires(job, s))
        retention.sweep_job(jid)
        self.assertEqual(self.clip(jid)["status"], "removed")  # still there
        retention.sweep_job(jid, now=time.time() + retention.keep_draft() + 60)
        self.assertNotIn(1, [c["idx"] for c in self.c.get("/api/clips").json["items"] if c["job"] == jid])

    def test_back_in_drafts_gets_a_full_draft_life(self):
        from web import retention
        from web.store import JOBS, LOCK
        jid = self.posted()
        with LOCK:
            for s in JOBS[jid]["shorts"]:
                s["edited_at"] = time.time() - 40 * UP.DAY
        self.gone_from_youtube(jid)
        self.c.post(f"/api/clips/{jid}/1/removed", json={"action": "draft"})
        job = F.job_json(jid)
        s = next(x for x in job["shorts"] if x["idx"] == 1)
        self.assertGreater(retention.draft_expires(job, s), time.time() + retention.keep_draft() - 60)
        retention.sweep_job(jid)
        self.assertEqual(self.clip(jid)["status"], "draft")

    def test_a_video_back_in_drafts_keeps_its_file_again(self):
        jid = self._vlog_removed()
        before = time.time()
        self.c.post(f"/api/vlogs/{jid}/removed", json={"action": "draft"})
        self.assertGreaterEqual(F.job_json(jid)["last_edit_at"], before)

    def test_only_its_owner(self):
        jid = self.posted()
        self.gone_from_youtube(jid)
        other = F.client(F.new_user())
        self.assertIn(other.post(f"/api/clips/{jid}/1/removed", json={"action": "clear"}).status_code, (403, 404))

    def _reel(self, jid):
        F.connect_instagram(self.u["id"])
        from web.store import update
        update(jid, ig_posts=[{"idx": 1, "status": "done", "media_id": "M1", "ig_id": "1789", "username": "x", "when": None,
                               "posted_at": "2026-10-01T10:00:00+00:00"}])

    def test_reel_gone_from_instagram_is_marked_and_other_errors_change_nothing(self):
        jid = self.posted()
        self._reel(jid)
        with mock.patch.object(RM.ig_http, "call", side_effect=InstagramError("busy", code=4)):
            self.assertEqual(RM.sync_instagram(self.u["id"]), 0)
        self.assertEqual(self.clip(jid)["instagram"]["state"], "posted")
        with mock.patch.object(RM.ig_http, "call", side_effect=InstagramError("gone", code=100)):
            self.assertEqual(RM.sync_instagram(self.u["id"]), 1)
        c = self.clip(jid)
        self.assertEqual(c["instagram"]["state"], "removed")
        self.assertEqual(c["status"], "posted")  # still on YouTube

    def test_gone_from_one_platform_keeps_the_other_when_cleared(self):
        jid = self.posted()
        self._reel(jid)
        self.gone_from_youtube(jid)
        self.assertEqual(self.clip(jid)["status"], "posted")
        self.c.post(f"/api/clips/{jid}/1/removed", json={"action": "clear"})
        c = self.clip(jid)
        self.assertIsNone(c["youtube"])
        self.assertEqual(c["instagram"]["state"], "posted")

    def _vlog_removed(self):
        up = F.upload(self.c, F.test_video(60))
        jid = self.c.post("/api/vlog/start", data={"upload": up}).json["id"]
        F.wait(lambda: F.job_json(jid).get("status") == "ready", timeout=30, what="ready")
        self.c.post(f"/api/vlog/{jid}/upload", json={"title": "Mine", "privacy": "public"})
        post = F.wait(lambda: (F.job_json(jid).get("vpost") or {}).get("state") == "done" and F.job_json(jid)["vpost"], what="sent")
        F.VIDEOS.pop(post["video_id"])
        YS.FRESH = 0
        try:
            YS.sync_deleted(self.u["id"], force=True)
        finally:
            YS.FRESH = 120
        self.assertEqual(F.job_json(jid)["vpost"]["state"], "removed")
        return jid

    def test_vlog_back_to_drafts_and_clear(self):
        jid = self._vlog_removed()
        self.assertTrue(self.c.post(f"/api/vlogs/{jid}/removed", json={"action": "draft"}).json["ok"])
        self.assertFalse(F.job_json(jid).get("vpost"))
        jid = self._vlog_removed()
        self.assertTrue(self.c.post(f"/api/vlogs/{jid}/removed", json={"action": "clear"}).json["ok"])
        self.assertEqual(F.job_json(jid)["vpost"]["state"], "cleared")

    def test_removed_vlog_forgets_its_video_id_after_30_days(self):
        jid = self._vlog_removed()
        UP.forget_removed_vlogs(self.u["id"], time.time() + 31 * UP.DAY)
        self.assertNotIn("video_id", F.job_json(jid)["vpost"])

    def test_daily_upkeep_does_all_of_it(self):
        jid = self.posted()
        self.outside("longvideo01", "Road trip", seconds=900)
        F.VIDEOS.pop(F.job_json(jid)["uploads"][0]["video_id"])
        UP.upkeep(self.u["id"])
        self.assertEqual(self.clip(jid)["status"], "removed")
        self.assertEqual([i["id"] for i in self.c.get("/api/channel-videos").json["items"]], ["longvideo01"])


if __name__ == "__main__":
    unittest.main()
