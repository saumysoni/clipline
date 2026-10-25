"""Analytics, against a strict YouTube Analytics stand-in and a sample Instagram account: every report, range and
content type, and that the numbers agree with each other (web/analytics*.py, youtube/analytics*.py, instagram/)."""
from tests import fakes as F

import time
import unittest
from datetime import date, datetime, timedelta, timezone

CH = "UCchannel000000000000001"
RANGES = {"7": "days=7", "28": "days=28", "90": "days=90", "365": "days=365", "all": "days=0"}


class Analytics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        F.install()
        F.reset()
        cls.u = F.new_user()
        cls.c = F.client(cls.u)
        F.connect_youtube(cls.u["id"], CH)
        F.connect_instagram(cls.u["id"])
        today = date.today()
        for vid, title, ago, kind, peak in (("oldshort0001", "Monsoon #Shorts", 40, "shorts", 900),
                                            ("oldshort0002", "Street food #Shorts", 120, "shorts", 1400),
                                            ("oldlong00001", "Road trip (full vlog)", 300, "videoOnDemand", 300),
                                            ("gonevideo001", "Deleted later", 60, "shorts", 300)):
            d = today - timedelta(days=ago)
            F.VIDEOS[vid] = {"title": title, "channel": CH, "published": d, "kind": kind, "peak": peak,
                             "publish_at": datetime.combine(d, datetime.min.time(), timezone.utc)}
        F.VIDEOS["gonevideo001"]["hidden"] = True
        cls.jid, st = F.make_shorts(cls.c, 300, 5)
        rows = [{"idx": s["idx"], "keep": True} for s in st["shorts"]]
        cls.c.post(f"/api/schedule/{cls.jid}", json={"shorts": rows, "schedule": "now", "channel": CH})
        F.wait(lambda: F.job_json(cls.jid).get("upload_status") == "done", what="posted")
        F.age_uploads(cls.jid)
        cls.c.post(f"/api/instagram/schedule/{cls.jid}", json={"shorts": rows, "schedule": "now"})
        F.wait(lambda: all(p["status"] == "done" for p in F.job_json(cls.jid).get("ig_posts") or [{"status": ""}]),
               what="Reels")

    def get(self, path):
        t = time.time()
        r = self.c.get(path)
        self.assertEqual(r.status_code, 200, f"{path}: {r.get_data(as_text=True)[:300]}")
        self.assertLess(time.time() - t, 10, f"{path} took too long")
        return r.json

    def test_dashboard_matrix(self):
        views = {}
        for content in ("shorts", "videos", "all"):
            for name, q in RANGES.items():
                qs = f"content={content}&{q}"
                y = self.get("/api/analytics?" + qs)["youtube"]
                self.assertTrue(y.get("full"), f"{qs}: {y.get('notes')}")
                t, daily = y["totals"], y.get("daily") or []
                views[(content, name)] = t["views"]
                if name != "all":
                    self.assertEqual(t["views"], sum(d["views"] for d in daily), qs)
                self.assertLessEqual(sum(x["views"] for x in y.get("shorts") or []), t["views"] + 1, qs)
                v = self.get("/api/analytics/videos?" + qs)
                other = (v.get("other") or {}).get("views") or 0
                self.assertEqual(v["total"]["views"], t["views"], qs)
                self.assertEqual(sum(x["views"] for x in v["videos"]) + other, v["total"]["views"], qs)
                if content != "videos" and name in ("90", "365", "all"):
                    self.assertGreater(other, 0, f"{qs}: a deleted video's views aren't shown as Other")
                csv = self.c.get("/api/analytics/videos.csv?" + qs).get_data(as_text=True)
                self.assertTrue(csv.strip().splitlines()[-1].startswith("Total"), qs)
                a = self.get("/api/analytics/audience?" + qs)
                self.assertIsNone(a.get("subscribed"), qs)  # YouTube answers 500 for it: left out, never an error
                if t["views"]:
                    self.assertTrue(a.get("devices"), qs)
        for content in ("shorts", "all"):
            v = [views[(content, k)] for k in ("7", "28", "90", "365", "all")]
            self.assertTrue(v[0] < v[1] < v[2] < v[3] <= v[4], f"{content}: {v}")
        self.assertEqual(views[("shorts", "28")] + views[("videos", "28")], views[("all", "28")])

    def test_custom_range_and_bad_range(self):
        s, e = date.today() - timedelta(9), date.today() - timedelta(3)
        y = self.get(f"/api/analytics?content=shorts&start={s}&end={e}")["youtube"]
        self.assertEqual((y["range"]["start"], y["range"]["end"]), (str(s), str(e)))
        self.assertEqual(y["totals"]["views"], sum(d["views"] for d in y["daily"]))
        r = self.c.get(f"/api/analytics?content=shorts&start={e}&end={s}")
        self.assertIn(r.status_code, (200, 400))  # never a crash
        self.assertEqual(self.c.get("/api/analytics?content=nonsense&days=abc").status_code in (200, 400), True)

    def test_all_time_starts_at_the_channel_not_2005(self):
        y = self.get("/api/analytics?content=all&days=0")["youtube"]
        self.assertGreaterEqual(y["range"]["start"], "2024-09-14")

    def test_one_short_and_compare(self):
        v = self.get("/api/analytics/videos?content=shorts&days=28")
        ids = [x["id"] for x in v["videos"]][:3]
        cm = self.get("/api/analytics/compare?content=shorts&days=28&ids=" + ",".join(ids))
        for ser in cm["series"]:
            row = next(x for x in v["videos"] if x["id"] == ser["id"])
            self.assertEqual(sum(x["views"] for x in ser["days"].values()), row["views"])
        one = self.get(f"/api/analytics/short/{ids[0]}?content=shorts&days=28")
        self.assertFalse(one["range"]["lifetime"])
        self.assertEqual(one["totals"]["views"], sum(x["views"] for x in one["daily"]))
        whole = self.get(f"/api/analytics/short/{ids[0]}?content=shorts&days=28&whole=1")
        self.assertTrue(whole["range"]["lifetime"])

    def test_first_week_and_both_apps(self):
        fw = self.get("/api/analytics/clips")["clips"]
        self.assertEqual(len(fw), 5)
        self.assertTrue(all(c["posted_at"] for c in fw))
        self.assertEqual([c["posted_at"] for c in fw], sorted(c["posted_at"] for c in fw))
        pairs = self.get("/api/analytics/pairs")["clips"]
        self.assertTrue(pairs)
        for c in pairs:
            if c.get("youtube"):
                self.assertTrue({"views", "likes", "comments", "shares", "subs"} <= set(c["youtube"]))
            if c.get("instagram"):
                self.assertTrue({"views", "likes", "comments", "shares", "follows"} <= set(c["instagram"]))
        self.assertIsNotNone(self.get("/api/analytics/pairs?vlog=../../x").get("clips"))
        self.assertIn("items", self.get("/api/analytics/vlogs?content=all&days=28"))

    def test_instagram_windows(self):
        ig = {q: self.get("/api/analytics/instagram?" + q) for q in ("days=7", "days=28", "days=30", "days=90", "days=365")}
        v = lambda q: (ig[q].get("totals") or {}).get("views") or 0  # noqa: E731
        self.assertTrue(v("days=7") < v("days=28") < v("days=90"))
        self.assertLessEqual(abs(v("days=90") - 3 * v("days=30")), 3)
        self.assertIsNone(ig["days=90"]["totals"].get("reach"))  # reach can't be added up over 30 days
        self.assertIsNotNone(ig["days=28"]["totals"].get("reach"))
        self.assertEqual((ig["days=365"]["note"], ig["days=365"]["days"]), ("cut", 90))
        old = self.get(f"/api/analytics/instagram?start={date.today() - timedelta(200)}&end={date.today() - timedelta(150)}")
        self.assertEqual(old["note"], "old")

    def test_pit_crews_read(self):
        first = self.get("/api/analytics/coach")
        self.assertTrue(first["headline"])
        read = F.wait(lambda: (r := self.get("/api/analytics/coach")).get("source") == "ai" and r, timeout=15,
                      what="the AI read")
        for p in ("youtube", "instagram"):
            self.assertGreaterEqual(sum(t["platform"] in (p, "both") for t in read["tips"]), 2)
        n = F.AI.kinds().count("coach")
        self.get("/api/analytics/coach?days=7&content=videos&plat=youtube")  # the range doesn't ask again
        self.assertEqual(F.AI.kinds().count("coach"), n)

    def test_read_never_quotes_an_invented_number(self):
        from youtube import analytics_coach as C
        allowed = C._numbers({"views": 1449, "pct": 53.4, "title": "700 Years of History"})
        self.assertTrue(C._honest("1,449 views, 53% from search, 700 Years", allowed))
        self.assertTrue(C._honest("3 clips", allowed))  # small counts are fine
        self.assertFalse(C._honest("12,345 new fans", allowed))
        F.AI.bad_numbers = True  # the AI invents "12,345 new fans" in its headline
        try:
            C._CACHE.clear()
            F.wait(lambda: (r := self.get("/api/analytics/coach")).get("source") == "ai" and r, timeout=15, what="read")
            read = self.get("/api/analytics/coach")
            self.assertNotIn("12,345", read["headline"])  # swapped for the rule-based headline
        finally:
            F.AI.bad_numbers = False

    def test_without_youtube_connection(self):
        c = F.client(F.new_user())
        r = c.get("/api/analytics?content=shorts&days=28")
        self.assertEqual(r.status_code, 200)


if __name__ == "__main__":
    unittest.main()
