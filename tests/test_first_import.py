"""Connecting an account for the first time: what's already on it comes in (web/first_import.py), Instagram's Reels are listed
(web/instagram_reels.py) and removed with the connection, and new accounts get Connect your accounts."""
from tests import _env  # noqa: F401  (first: clean settings)

import time
import unittest
from datetime import datetime, timezone
from unittest import mock

from tests import fakes as F
from accounts import db
from instagram.http import InstagramError
from instagram.reels import account_reels, title_of
import web.channel_videos as CV
import web.first_import as FI
import web.instagram_deletion as DEL
import web.instagram_reels as IR
import web.youtube_upkeep as UP

CH = "UCchannel000000000000001"
IG_ID = "1789"


class Base(unittest.TestCase):
    def setUp(self):
        F.install()
        F.reset()
        for s in (CV._RUNNING, CV._ASKED, IR._RUNNING, IR._TRIED, FI._IMPORTS):
            s.clear()
        self.u = F.new_user()
        self.uid = self.u["id"]
        self.c = F.client(self.u)
        self.on = mock.patch.dict("os.environ", {"INSTAGRAM_APP_ID": "a", "INSTAGRAM_APP_SECRET": "b"})
        self.on.start()
        self.addCleanup(self.on.stop)

    def video(self, vid, title, seconds):
        F.VIDEOS[vid] = {"title": title, "channel": CH, "privacy": "public", "seconds": seconds}

    def reel(self, mid, caption="A caption", ig_id=IG_ID):
        F.REELS[mid] = {"caption": caption, "ig_id": ig_id, "thumb": f"https://scontent.cdninstagram.com/{mid}.jpg",
                        "posted": datetime(2026, 10, 1, 12, tzinfo=timezone.utc)}

    def settled(self):
        return F.wait(lambda: (lambda j: j if not any(x["state"] == "running" for x in j["imports"]) else None)(
            self.c.get("/api/import/status").json), what="import finished")


class YouTubeFirstRead(Base):
    def test_connecting_reads_the_channel_and_counts_videos_and_shorts(self):
        self.video("longvideo01", "Road trip", 900)
        self.video("longvideo02", "City walk", 800)
        self.video("shortvid001", "Quick #shorts", 40)
        F.connect_youtube(self.uid)
        j = self.c.post("/api/import/begin").json
        self.assertEqual(len(j["imports"]), 1)
        row = self.settled()["imports"][0]
        self.assertEqual((row["state"], row["videos"], row["shorts"], row["platform"]), ("done", 2, 1, "youtube"))
        self.assertEqual(len(self.c.get("/api/channel-videos").json["items"]), 3)

    def test_it_happens_only_once_for_an_account(self):
        F.connect_youtube(self.uid)
        self.c.post("/api/import/begin")
        self.settled()
        self.c.post("/api/import/seen")
        with mock.patch.object(CV, "refresh_channel") as read:
            j = self.c.post("/api/import/begin").json
        read.assert_not_called()
        self.assertEqual(j["imports"], [])

    def test_a_second_channel_gets_its_own_first_read(self):
        F.connect_youtube(self.uid)
        self.c.post("/api/import/begin")
        self.settled()
        self.c.post("/api/import/seen")
        F.connect_youtube(self.uid, channel="UCchannel000000000000002", title="Second")
        names = [x["name"] for x in self.c.post("/api/import/begin").json["imports"]]
        self.assertEqual(names, ["Second"])

    def test_a_failed_read_says_so_and_stays_unread_for_the_daily_read(self):
        F.connect_youtube(self.uid)
        with mock.patch("youtube.channel_videos", side_effect=RuntimeError("quota")):
            self.c.post("/api/import/begin")
            row = self.settled()["imports"][0]
        self.assertEqual(row["state"], "error")
        self.assertIsNone(db.channel_checked(self.uid, CH))
        self.assertNotIn(self.uid, CV._RUNNING)

    def test_a_reader_stuck_or_seen_is_not_shown_again(self):
        F.connect_youtube(self.uid)
        self.c.post("/api/import/begin")
        self.c.post("/api/import/seen")
        self.assertEqual(self.c.get("/api/import/status").json["imports"], [])

    def test_only_the_creators_own_imports_are_reported(self):
        F.connect_youtube(self.uid)
        self.c.post("/api/import/begin")
        other = F.client(F.new_user())
        self.assertEqual(other.get("/api/import/status").json["imports"], [])

    def test_needs_sign_in(self):
        self.assertEqual(F.client().get("/api/import/status").status_code, 401)


class SignInNeverFails(Base):
    def test_a_read_that_cannot_start_does_not_fail_the_sign_in(self):
        with mock.patch.object(FI, "begin", side_effect=RuntimeError("boom")):
            FI.begin_safely(self.uid)  # no exception

    def test_personal_is_reported_on_an_instagram_import(self):
        F.connect_instagram(self.uid, account_type="PERSONAL")
        self.assertTrue(self.c.post("/api/import/begin").json["imports"][0]["personal"])


class InstagramReels(Base):
    def test_titles_are_the_captions_first_line(self):
        self.assertEqual(title_of("\n  Big day  \nsecond line #tag"), "Big day")
        self.assertEqual(title_of(""), "Instagram Reel")
        self.assertEqual(len(title_of("x" * 400)), 100)

    def test_only_reels_are_read_across_pages(self):
        F.connect_instagram(self.uid)
        pages = [{"data": [{"id": "1", "media_product_type": "REELS", "caption": "One", "timestamp": "t", "permalink": "p", "thumbnail_url": "u"},
                           {"id": "2", "media_product_type": "FEED", "caption": "A photo"}],
                  "paging": {"cursors": {"after": "AA"}, "next": "https://x"}},
                 {"data": [{"id": "3", "media_product_type": "REELS"}], "paging": {"cursors": {"after": "BB"}}}]
        seen = []

        def call(method, url, params=None, **kw):
            seen.append(params.get("after"))
            return pages.pop(0)
        with mock.patch("instagram.reels.call", call):
            rows = account_reels(self.uid, IG_ID)
        self.assertEqual([r["id"] for r in rows], ["1", "3"])
        self.assertEqual(seen, [None, "AA"])

    def test_first_read_lists_reels_on_shorts_and_reels_not_videos(self):
        self.reel("9001", "Sunset drive\nmore words")
        F.connect_instagram(self.uid)
        self.c.post("/api/import/begin")
        row = self.settled()["imports"][0]
        self.assertEqual((row["state"], row["reels"], row["name"]), ("done", 1, "@pitcrew.test"))
        item = self.c.get("/api/channel-videos").json["items"][0]
        self.assertEqual(item["platform"], "instagram")
        self.assertEqual(item["title"], "Sunset drive")
        self.assertTrue(item["short"])  # the Videos page shows only long ones
        self.assertEqual(item["url"], "https://www.instagram.com/reel/9001/")
        self.assertTrue(item["published"].endswith("Z"))

    def test_only_this_accounts_reels_and_not_what_pit_crew_posted(self):
        self.reel("9001")
        self.reel("9002", ig_id="other")
        self.reel("9003")
        jid, _ = F.make_shorts(self.c, count=1)
        from web.store import JOBS, LOCK, update
        with LOCK:
            JOBS[jid]["ig_posts"] = [{"media_id": "9003", "ig_id": IG_ID, "status": "posted"}]
        update(jid)
        F.connect_instagram(self.uid)
        IR.refresh_user(self.uid)
        self.assertEqual([i["id"] for i in self.c.get("/api/channel-videos").json["items"]], ["9001"])

    def test_a_deleted_reel_goes_at_the_next_read_and_a_failed_read_changes_nothing(self):
        self.reel("9001")
        self.reel("9002")
        F.connect_instagram(self.uid)
        IR.refresh_user(self.uid)
        F.REELS.pop("9002")
        with mock.patch("instagram.account_reels", side_effect=InstagramError("busy")):
            self.assertFalse(IR.refresh_account(self.uid, IG_ID))
        self.assertEqual(len(db.instagram_reel_rows(self.uid)), 2)
        IR.refresh_user(self.uid)
        self.assertEqual([r["media_id"] for r in db.instagram_reel_rows(self.uid)], ["9001"])

    def test_the_daily_upkeep_reads_them(self):
        self.reel("9001")
        F.connect_instagram(self.uid)
        UP.upkeep(self.uid)
        self.assertEqual(len(db.instagram_reel_rows(self.uid)), 1)
        self.assertTrue(db.channel_checked(self.uid, IG_ID))

    def test_opening_the_page_reads_only_when_a_day_old_and_backs_off_after_failures(self):
        F.connect_instagram(self.uid)
        now = time.time()
        with mock.patch("instagram.account_reels", side_effect=InstagramError("busy")) as read:
            IR.refresh_if_old(self.uid, now)
            F.wait(lambda: self.uid not in IR._RUNNING, what="read")
            IR.refresh_if_old(self.uid, now + 60)
            F.wait(lambda: self.uid not in IR._RUNNING, what="read")
            self.assertEqual(read.call_count, 1)
        IR.refresh_user(self.uid, now)
        with mock.patch("instagram.account_reels") as read:
            IR._TRIED.clear()
            IR.refresh_if_old(self.uid, now + 60)
            read.assert_not_called()

    def test_disconnecting_forgets_them_and_connecting_again_is_a_first_time(self):
        self.reel("9001")
        F.connect_instagram(self.uid)
        IR.refresh_user(self.uid)
        self.c.post("/api/instagram/signout", json={"ig_id": IG_ID})
        self.assertEqual(db.instagram_reel_rows(self.uid), [])
        self.assertIsNone(db.channel_checked(self.uid, IG_ID))

    def test_removal_through_meta_forgets_them(self):
        self.reel("9001")
        F.connect_instagram(self.uid)
        IR.refresh_user(self.uid)
        DEL.forget_account(IG_ID, everything=False)
        self.assertEqual(db.instagram_reel_rows(self.uid), [])

    def test_disconnected_during_the_read_keeps_nothing(self):
        F.connect_instagram(self.uid)

        def read(uid, ig_id):
            db.drop_connection(db.connection(uid, "instagram", ig_id)["id"])
            return [{"id": "1", "title": "t", "published": "", "permalink": "", "thumb": ""}]
        with mock.patch("instagram.account_reels", read):
            self.assertFalse(IR.refresh_account(self.uid, IG_ID))
        self.assertEqual(db.instagram_reel_rows(self.uid), [])

    def test_deleting_the_account_removes_them(self):
        self.reel("9001")
        F.connect_instagram(self.uid)
        IR.refresh_user(self.uid)
        db.delete_user(self.uid)
        self.assertEqual(db.instagram_reel_rows(self.uid), [])

    def test_addresses_that_are_not_instagrams_are_never_passed_on(self):
        F.connect_instagram(self.uid)
        db.replace_instagram_reels(self.uid, IG_ID, [{"id": "1", "title": "t", "published": "", "permalink": "javascript:alert(1)", "thumb": "http://x/y.jpg"}])
        item = IR.reel_items(self.uid)[0]
        self.assertEqual((item["url"], item["thumb"]), ("", ""))


class Welcome(Base):
    def status(self, c):
        with mock.patch("youtube.is_configured", return_value=True):
            return c.get("/api/import/status").json

    def test_new_accounts_see_it_until_they_skip(self):
        u = F.new_user(onboarded=False)
        c = F.client(u)
        self.assertTrue(self.status(c)["welcome"])
        c.post("/api/import/seen")
        self.assertFalse(self.status(c)["welcome"])

    def test_gone_once_something_is_connected(self):
        u = F.new_user(onboarded=False)
        F.connect_youtube(u["id"])
        self.assertFalse(self.status(F.client(u))["welcome"])

    def test_people_already_here_never_see_it(self):
        u = F.new_user(onboarded=False)
        with db.connect() as con:
            con.execute("PRAGMA user_version = 2")
            con.execute("UPDATE users SET onboarded_at = NULL WHERE id = ?", (u["id"],))
        db.init()
        self.assertTrue(db.onboarded(u["id"]))
        self.assertFalse(self.status(F.client(u))["welcome"])

    def test_not_shown_when_nothing_can_be_connected(self):
        u = F.new_user(onboarded=False)
        with mock.patch("youtube.is_configured", return_value=False), mock.patch("instagram.is_configured", return_value=False):
            self.assertFalse(F.client(u).get("/api/import/status").json["welcome"])


if __name__ == "__main__":
    unittest.main()
