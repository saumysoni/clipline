"""YouTube's shared daily upload limit (web/youtube_quota.py): open until 60%, then fair shares, and anything over waits
in Pit Crew and goes up after the reset instead of failing."""
from tests import fakes as F

import json
import os
import unittest
from datetime import datetime, timedelta, timezone

from accounts import db
from web import youtube_quota as Q

CH_A, CH_B = "UCchannel00000000000000A", "UCchannel00000000000000B"


class Base(unittest.TestCase):
    def setUp(self):
        F.install()
        F.reset()
        os.environ.update(YOUTUBE_DAILY_UPLOADS="20", YOUTUBE_OPEN_SHARE="60", YOUTUBE_RESERVE="2")  # open 12, pool 6
        with db.connect() as con:
            con.execute("DELETE FROM youtube_uploads")

    def tearDown(self):
        for k in ("YOUTUBE_DAILY_UPLOADS", "YOUTUBE_OPEN_SHARE", "YOUTUBE_RESERVE"):
            os.environ.pop(k, None)

    def creator(self, channel, shorts=3, seconds=300):
        u = F.new_user()
        c = F.client(u)
        F.connect_youtube(u["id"], channel)
        jid, st = F.make_shorts(c, seconds, shorts)
        return u, c, jid, st

    def post(self, c, jid, idxs, schedule="now", **extra):
        r = c.post(f"/api/schedule/{jid}", json={"shorts": [{"idx": i, "keep": True} for i in idxs],
                                                 "schedule": schedule, "tz": "UTC", **extra})
        self.assertEqual(r.status_code, 200, r.json)
        return F.wait(lambda: F.job_json(jid).get("upload_status") in ("done", "error") and F.job_json(jid), what="posting")


def fill(n, user_id=999990):
    """n uploads by other creators today (straight into the count)."""
    for _ in range(n):
        db.add_youtube_upload(Q.today(), user_id)


class Rules(Base):
    def test_numbers(self):
        self.assertEqual((Q.limit(), Q.open_until(), Q.reserve()), (20, 12, 2))
        u = F.new_user()
        for _ in range(12):
            self.assertEqual(Q.take(u["id"]), "open")  # the open part: no cap per creator
        # after 12: pool 6, shared by the creators posting today + room for one more
        self.assertEqual(Q.status(u["id"])["left_today"], 3)  # {u} + 1 -> 6 // 2
        self.assertEqual([Q.take(u["id"]) for _ in range(4)], ["fair", "fair", "fair", None])
        other = F.new_user()
        self.assertEqual(Q.status(other["id"])["left_today"], 2)  # {u, other} + 1 -> 6 // 3
        self.assertEqual([Q.take(other["id"]) for _ in range(3)], ["fair", "fair", None])
        self.assertEqual(Q.status(other["id"])["day_left"], 1)
        self.assertIsNone(Q.take(u["id"]))  # 17 used: only the reserve (and 1 spare) is left
        self.assertEqual([Q.take(u["id"], "replace") for _ in range(4)], ["open", "open", "open", None])  # up to 20

    def test_days_are_pacific_and_reset(self):
        u = F.new_user()
        # 07:30 UTC = 00:30 Pacific (PDT): already the next day
        late = datetime(2026, 10, 26, 6, 59, tzinfo=timezone.utc).timestamp()
        early = datetime(2026, 10, 26, 7, 1, tzinfo=timezone.utc).timestamp()
        self.assertNotEqual(Q.today(late), Q.today(early))
        for _ in range(18):
            Q.take(u["id"], now=late)
        self.assertIsNone(Q.take(u["id"], now=late))
        self.assertEqual(Q.take(u["id"], now=early), "open")  # a new day
        self.assertEqual(Q.resets_at(late).isoformat(), "2026-10-26T07:00:00+00:00")


class WaitInsteadOfFail(Base):
    def test_over_the_limit_waits_then_goes_up_after_the_reset(self):
        a, ca, ja, _ = self.creator(CH_A, 5)
        fill(12, 999999)  # someone else used the open part of the day
        db.add_youtube_upload(Q.today(), 999999, fair=True)
        db.add_youtube_upload(Q.today(), 999999, fair=True)  # and 2 of the fair part
        start = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
        job = self.post(ca, ja, [1, 2, 3, 4, 5], "custom", start=start, every=24, channel=CH_A)
        self.assertEqual(job["upload_status"], "done")  # not an error
        went = sorted(u["idx"] for u in job["uploads"])
        waiting = sorted(w["idx"] for w in job["yt_waiting"])
        self.assertEqual(len(went), 2)  # 6 // ({999999, a} + 1) = 2
        self.assertEqual(sorted(went + waiting), [1, 2, 3, 4, 5])
        self.assertIn("after midnight Pacific", job["upload_msg"])
        clips = {c["idx"]: c for c in ca.get("/api/clips").json["items"]}
        self.assertEqual(clips[waiting[0]]["status"], "scheduled")
        self.assertTrue(clips[waiting[0]]["youtube"]["waiting"])
        r = ca.post(f"/api/schedule/{ja}", json={"shorts": [{"idx": waiting[0], "keep": True}], "schedule": "now"})
        self.assertEqual(r.status_code, 400)  # never planned twice
        self.assertEqual(ca.get("/api/youtube/today").json["waiting"], 3)
        planned = {w["idx"]: w["when"] for w in job["yt_waiting"]}
        # midnight Pacific: a new day
        with db.connect() as con:
            con.execute("DELETE FROM youtube_uploads")
        Q.send_waiting()
        job = F.wait(lambda: F.job_json(ja).get("upload_status") == "done" and len(F.job_json(ja)["uploads"]) == 5
                     and F.job_json(ja), what="waiting Shorts sent")
        self.assertEqual(job.get("yt_waiting"), [])
        for u in job["uploads"]:
            if u["idx"] in planned:
                self.assertEqual(u["when"], planned[u["idx"]])  # the times the creator chose stay

    def test_a_time_that_passed_while_waiting_goes_public_now(self):
        a, ca, ja, _ = self.creator(CH_A, 1, 60)
        fill(18)  # the day is used up (all but the reserve)
        soon = (datetime.now(timezone.utc) + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")
        self.post(ca, ja, [1], "custom", start=soon)
        with Q.LOCK:
            job = Q.load_job(ja)
            job["yt_waiting"][0]["when"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        with db.connect() as con:
            con.execute("DELETE FROM youtube_uploads")
        Q.send_waiting()
        up = F.wait(lambda: F.job_json(ja)["uploads"] and F.job_json(ja)["uploads"][0], what="sent")
        self.assertIsNone(up["when"])  # public as soon as it's up

    def test_youtube_says_used_up_first(self):
        import httplib2
        from googleapiclient.errors import HttpError
        import youtube
        a, ca, ja, _ = self.creator(CH_A, 2, 150)
        real = youtube.upload_short

        def refuse(*a_, **k):
            raise HttpError(httplib2.Response({"status": 403}), json.dumps(
                {"error": {"errors": [{"reason": "quotaExceeded"}], "code": 403}}).encode())
        youtube.upload_short = refuse
        try:
            job = self.post(ca, ja, [1, 2])
        finally:
            youtube.upload_short = real
        self.assertEqual(job["upload_status"], "done")
        self.assertEqual(len(job["yt_waiting"]), 2)
        self.assertTrue(db.youtube_exhausted(Q.today()))
        self.assertEqual(Q.status(a["id"])["mine_today"], 0)  # the refused uploads weren't counted

    def test_vlog_upload_waits_too(self):
        u = F.new_user()
        c = F.client(u)
        F.connect_youtube(u["id"], CH_A)
        up = F.upload(c, F.test_video(60))
        jid = c.post("/api/vlog/start", data={"upload": up}).json["id"]
        F.wait_ready(c, jid)
        fill(18)  # the day is used up (all but the reserve)
        c.post(f"/api/vlog/{jid}/upload", json={"privacy": "public"})
        post = F.wait(lambda: F.job_json(jid)["vpost"]["state"] == "waiting" and F.job_json(jid)["vpost"], what="waiting")
        self.assertIn("The vlog will go up", post["note"])
        self.assertEqual(c.post(f"/api/vlog/{jid}/upload", json={}).status_code, 400)
        with db.connect() as con:
            con.execute("DELETE FROM youtube_uploads")
        Q.send_waiting()
        F.wait(lambda: F.job_json(jid)["vpost"]["state"] == "done", what="vlog sent")

    def test_replace_never_waits_silently(self):
        a, ca, ja, _ = self.creator(CH_A, 1, 60)
        start = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
        self.post(ca, ja, [1], "custom", start=start)
        fill(20)  # every upload of the day, the reserve too
        from web.store import update_short
        update_short(ja, 1, video="short_1_v2.mp4")
        F.copy_into(ja, F.TMP / "jobs" / ja / "short_1.mp4", "short_1_v2.mp4")
        ca.post(f"/api/repost/{ja}/1", json={})
        job = F.wait(lambda: F.job_json(ja).get("upload_status") in ("done", "error") and F.job_json(ja), what="replace")
        self.assertEqual(job["upload_status"], "error")
        self.assertIn("after midnight Pacific", job["upload_msg"])


if __name__ == "__main__":
    unittest.main()
