"""YouTube's data rules (web/youtube_upkeep.py): refresh within 30 days, forget a disconnected channel in time."""
from tests import _env  # noqa: F401  (first: throwaway folders)

import json
import time
import unittest

from accounts import db
from settings import JOBS_DIR

import youtube as yt
from web import youtube_upkeep as up
from web.store import JOBS
from youtube import analytics, analytics_coach

DAY = 24 * 3600


def save_job(job):
    (JOBS_DIR / job["id"]).mkdir(parents=True, exist_ok=True)
    (JOBS_DIR / job["id"] / "job.json").write_text(json.dumps(job), encoding="utf-8")
    JOBS.pop(job["id"], None)


def read_job(job_id):
    JOBS.pop(job_id, None)
    return json.loads((JOBS_DIR / job_id / "job.json").read_text(encoding="utf-8"))


class Upkeep(unittest.TestCase):
    def setUp(self):
        db.init()
        self.uid = db.create_user(f"u{time.time_ns()}@example.com", "U")
        self.now = time.time()
        self.calls = []
        self._real = (yt.recheck, yt.fetch_video_info, yt.access_token, up.sync_deleted)
        yt.recheck = lambda row: self.calls.append(("recheck", row["account_id"])) or "ok"
        yt.access_token = lambda *a, **k: None
        up.sync_deleted = lambda uid, force=False: self.calls.append(("sync", uid)) or 0

    def tearDown(self):
        yt.recheck, yt.fetch_video_info, yt.access_token, up.sync_deleted = self._real

    def connect(self, channel, checked_at=None):
        db.save_connection(self.uid, "youtube", channel, {"token": "t", "scopes": []},
                           {"id": channel, "title": channel, **({"checked_at": checked_at} if checked_at else {})})

    def shorts_job(self, jid, channel, **extra):
        save_job({"id": jid, "owner": self.uid, "status": "done", "created_at": self.now - 40 * DAY,
                  "shorts": [{"idx": 1, "title": "A", "video": "short_1.mp4"}, {"idx": 2, "title": "B", "video": "short_2.mp4"}],
                  "uploads": [{"idx": 1, "video_id": "vid1", "channel": channel, "video": "short_1.mp4"},
                              {"idx": 2, "video_id": "vid2", "channel": "UCother", "video": "short_2.mp4"}], **extra})

    def test_channels_rechecked_weekly(self):
        self.connect("UCfresh", checked_at=self.now - DAY)
        self.connect("UCstale", checked_at=self.now - 8 * DAY)
        self.connect("UCnever")
        up.recheck_channels(self.uid, self.now)
        self.assertEqual(sorted(c[1] for c in self.calls if c[0] == "recheck"), ["UCnever", "UCstale"])

    def test_gone_channel_forgotten_after_grace(self):
        self.connect("UCother")
        self.shorts_job("aaaaaaaaa1", "UCgone")
        analytics._WEEK[("UCgone", "vid1")] = (self.now, 10, True)
        analytics._WEEK[("UCother", "vid2")] = (self.now, 5, True)
        self.assertEqual(up.forget_gone_channels(self.uid, self.now), [])  # noted, not deleted yet
        self.assertEqual(len(read_job("aaaaaaaaa1")["uploads"]), 2)
        self.assertEqual(up.forget_gone_channels(self.uid, self.now + 4 * DAY), [])
        self.assertEqual(up.forget_gone_channels(self.uid, self.now + 5 * DAY + 1), ["UCgone"])
        ups = read_job("aaaaaaaaa1")["uploads"]
        self.assertEqual([u["channel"] for u in ups], ["UCother"])  # the connected channel's record stays
        self.assertNotIn(("UCgone", "vid1"), analytics._WEEK)
        self.assertIn(("UCother", "vid2"), analytics._WEEK)

    def test_reconnecting_in_time_keeps_everything(self):
        self.connect("UCother")
        self.shorts_job("aaaaaaaaa2", "UCback")
        up.forget_gone_channels(self.uid, self.now)
        self.connect("UCback")
        up.forget_gone_channels(self.uid, self.now + 3 * DAY)
        self.assertEqual(up.forget_gone_channels(self.uid, self.now + 10 * DAY), [])
        self.assertEqual(len(read_job("aaaaaaaaa2")["uploads"]), 2)

    def test_vlog_upload_on_gone_channel(self):
        save_job({"id": "aaaaaaaaa3", "owner": self.uid, "kind": "vlog", "status": "ready",
                  "vpost": {"state": "done", "video_id": "vlogvid", "channel": "UCgone2"},
                  "vlog": {"title": "My trip", "video_id": "vlogvid", "youtube_url": "https://youtu.be/vlogvid",
                           "channel": "Me", "channel_handle": "@me"}, "uploads": []})
        up.forget_gone_channels(self.uid, self.now)
        up.forget_gone_channels(self.uid, self.now + 6 * DAY)
        job = read_job("aaaaaaaaa3")
        self.assertNotIn("video_id", job["vpost"])
        self.assertNotIn("channel", job["vpost"])
        self.assertEqual(job["vpost"]["state"], "done")
        self.assertEqual(job["vlog"], {"title": "My trip"})

    def test_busy_job_is_left_for_later(self):
        self.connect("UCother")
        self.shorts_job("aaaaaaaaa4", "UCgone3")
        JOBS["aaaaaaaaa4"] = {**read_job("aaaaaaaaa4"), "status": "working"}  # being remade right now (in memory)
        up.forget_gone_channels(self.uid, self.now)
        up.forget_gone_channels(self.uid, self.now + 6 * DAY)
        self.assertEqual(len(JOBS["aaaaaaaaa4"]["uploads"]), 2)
        JOBS["aaaaaaaaa4"]["status"] = "done"  # finished: forgotten on the next day's check
        up.forget_gone_channels(self.uid, self.now + 7 * DAY)
        self.assertEqual(len(read_job("aaaaaaaaa4")["uploads"]), 1)

    def link_job(self, jid, fetched_days_ago):
        save_job({"id": jid, "owner": self.uid, "status": "done", "created_at": self.now - 60 * DAY,
                  "vlog": {"title": "Typed title", "youtube_url": "https://www.youtube.com/watch?v=abcdefghijk",
                           "description": "old", "tags": ["a"], "channel": "Chan", "channel_id": "UCx",
                           "channel_handle": "@x", "video_id": "abcdefghijk", "complete": True,
                           "fetched_at": self.now - fetched_days_ago * DAY}})

    def test_link_details_read_again_after_30_days(self):
        self.link_job("aaaaaaaaa5", 31)
        self.link_job("aaaaaaaaa6", 10)
        yt.fetch_video_info = lambda url, token=None: {"video_id": "abcdefghijk", "title": "New", "description": "new",
                                                       "tags": ["b"], "channel": "Chan", "channel_id": "UCx",
                                                       "channel_handle": "@x", "complete": True}
        up.refresh_vlog_links(self.uid, self.now)
        v = read_job("aaaaaaaaa5")["vlog"]
        self.assertEqual((v["description"], v["tags"], v["title"]), ("new", ["b"], "Typed title"))
        self.assertAlmostEqual(v["fetched_at"], self.now)
        self.assertEqual(read_job("aaaaaaaaa6")["vlog"]["description"], "old")  # not due yet

    def test_link_details_deleted_when_youtube_has_no_video(self):
        self.link_job("aaaaaaaaa7", 31)

        def gone(url, token=None):
            raise RuntimeError("YouTube couldn't find that video. Is it public or unlisted, not private?")
        yt.fetch_video_info = gone
        up.refresh_vlog_links(self.uid, self.now)
        v = read_job("aaaaaaaaa7")["vlog"]
        self.assertEqual(set(v), {"title", "youtube_url", "fetched_at"})

    def test_link_offline_retried_then_deleted_after_a_week(self):
        self.link_job("aaaaaaaaa8", 31)

        def offline(url, token=None):
            raise RuntimeError("Couldn't reach YouTube. Check your internet connection.")
        yt.fetch_video_info = offline
        up.refresh_vlog_links(self.uid, self.now)
        self.assertEqual(read_job("aaaaaaaaa8")["vlog"]["description"], "old")
        up.refresh_vlog_links(self.uid, self.now + 7 * DAY)
        self.assertNotIn("description", read_job("aaaaaaaaa8")["vlog"])

    def test_numbers_in_memory_expire(self):
        analytics._CACHE[("u", "UCa", 28)] = (self.now - 3600, {})
        analytics._CACHE[("u", "UCa", 7)] = (self.now, {})
        analytics._WEEK[("UCa", "old")] = (self.now - 31 * DAY, 1, True)
        analytics_coach._CACHE[("u", "UCa", True, "2026-01-01")] = (self.now - 1, {})
        yt.forget_old_numbers(now=self.now)
        self.assertNotIn(("u", "UCa", 28), analytics._CACHE)
        self.assertIn(("u", "UCa", 7), analytics._CACHE)
        self.assertNotIn(("UCa", "old"), analytics._WEEK)
        self.assertNotIn(("u", "UCa", True, "2026-01-01"), analytics_coach._CACHE)

    def test_sweep_covers_every_account(self):
        self.connect("UCs")
        up.sweep(now=self.now)
        self.assertIn(("sync", self.uid), self.calls)


class Recheck(unittest.TestCase):
    """youtube/connection.recheck: refreshes the channel's details, never acts on a surprise."""

    def setUp(self):
        from youtube import connection
        self.c = connection
        self._real = (connection.load_creds, connection._lookup_channel, connection.db.update_connection)
        self.saved = []
        connection.db.update_connection = lambda cid, token=None, profile=None: self.saved.append(profile)

    def tearDown(self):
        self.c.load_creds, self.c._lookup_channel, self.c.db.update_connection = self._real

    def row(self):
        return {"id": 1, "user_id": 1, "account_id": "UCme", "token": {"scopes": list(self.c.SCOPES)}}

    def test_ok_saves_fresh_details(self):
        self.c.load_creds = lambda uid, channel=None, row=None: type("C", (), {"token": "t"})()
        self.c._lookup_channel = lambda tok: {"id": "UCme", "title": "New name", "handle": "@me", "thumb": ""}
        self.assertEqual(self.c.recheck(self.row()), "ok")
        self.assertEqual(self.saved[0]["title"], "New name")
        self.assertIn("checked_at", self.saved[0])

    def test_revoked(self):
        self.c.load_creds = lambda uid, channel=None, row=None: None
        self.assertEqual(self.c.recheck(self.row()), "gone")
        self.assertEqual(self.saved, [])

    def test_offline_or_other_channel_changes_nothing(self):
        def offline(*a, **k):
            raise OSError("Couldn't reach Google")
        self.c.load_creds = offline
        self.assertEqual(self.c.recheck(self.row()), "offline")
        self.c.load_creds = lambda uid, channel=None, row=None: type("C", (), {"token": "t"})()
        self.c._lookup_channel = lambda tok: {"id": "UCsomeoneelse", "title": "", "handle": "", "thumb": ""}
        self.assertEqual(self.c.recheck(self.row()), "offline")
        self.assertEqual(self.saved, [])


if __name__ == "__main__":
    unittest.main()
