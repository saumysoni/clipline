"""AI Edit (pipeline/pieces.py, pipeline/ai_edit.py, web/ai_edit.py): a Short that keeps several pieces of its moment,
pauses and filler words found from the word timings, the AI's shorter version and suggested cuts, and applying them."""
from tests import fakes as F

import unittest

from pipeline import ai_edit as AE
from pipeline import pieces as P
from settings import JOBS_DIR


def W(*spec):
    """Words from (text, start, end) tuples."""
    return [{"w": w, "s": s, "e": e} for w, s, e in spec]


class Pieces(unittest.TestCase):
    def test_normalize_subtract_length(self):
        self.assertEqual(P.normalize([(5, 8), (1, 3), (2.98, 4), (9, 9.1)], 0, 10), [(1, 4), (5, 8)])  # joined, tiny dropped
        self.assertEqual(P.normalize([(-2, 3), (8, 20)], 0, 10), [(0, 3), (8, 10)])  # clipped to the moment
        m = {"start": 0, "end": 10}
        self.assertEqual(P.kept(m), [(0, 10)])
        self.assertEqual(P.subtract([(0, 10)], [(2, 3), (6, 7)], 0, 10), [(0, 2), (3, 6), (7, 10)])
        self.assertEqual(P.length({**m, "pieces": [[0, 2], [3, 6]]}), 5)

    def test_words_follow_the_joined_clock(self):
        words = W(("one", 1, 1.4), ("two", 2, 2.4), ("three", 5, 5.4), ("four", 8, 8.4))
        m = {"start": 0, "end": 10, "pieces": [[0, 3], [7, 10]]}
        tl = P.timeline(m, words)
        self.assertEqual([w["w"] for w in tl], ["one", "two", "four"])  # "three" was cut
        self.assertAlmostEqual(tl[-1]["s"], 3 + 1)  # 8 s in the vlog = 3 s of the first piece + 1 s into the second
        self.assertEqual(P.said({"words": words}, m), "one two four")
        self.assertIsNone(P.to_short(P.kept(m), 5))


class Finders(unittest.TestCase):
    words = W(("so", 0.5, 0.8), ("um", 0.9, 1.1), ("we", 1.2, 1.4), ("went", 3.0, 3.3), ("up", 3.4, 3.6))

    def test_pauses_long_and_tight(self):
        m = {"start": 0, "end": 4.5}
        long = AE.pauses(self.words, m, "long")
        self.assertIn((1.52, 2.88, 1.36), long)  # 1.4 -> 3.0, a breath kept each side
        self.assertTrue(any(b == 4.5 for a, b, _ in long))  # the quiet after the last word goes (a breath kept)
        self.assertGreaterEqual(len(AE.pauses(self.words, m, "tight")), len(long))

    def test_fillers(self):
        got = AE.fillers(self.words, {"start": 0, "end": 4.5})
        self.assertEqual([f[2] for f in got], ["um"])
        a, b, _ = got[0]
        self.assertTrue(0.8 <= a <= 0.9 and 1.1 <= b <= 1.2)  # never into "so" or "we"

    def test_a_cut_hook_number_is_dropped(self):
        m = {"start": 0, "end": 9, "hook": "I lost 2000 dollars", "hook_mode": "text", "hook_style": "bold",
             "hooks": {"bold": "I lost 2000 dollars", "story": "So this happened"}}
        fix, note = AE.honest_hooks(m, "so we went up the hill")
        self.assertEqual(fix["hook"], "So this happened")
        self.assertNotIn("bold", fix["hooks"])
        self.assertIn("no longer said", note)
        self.assertEqual(AE.honest_hooks(m, "and I lost 2000 dollars there"), ({}, ""))


class Routes(unittest.TestCase):
    def setUp(self):
        F.install()
        F.reset()
        self.u = F.new_user()
        self.c = F.client(self.u)
        self.jid, st = F.make_shorts(self.c, 150, 2)
        self.s = st["shorts"][0]
        self.base = f"/api/ai-edit/{self.jid}/{self.s['idx']}"

    def short(self):
        return F.wait(lambda: (x := next(y for y in F.job_json(self.jid)["shorts"] if y["idx"] == self.s["idx"]))
                      and not x.get("retrying") and x, what="remade")

    def test_info(self):
        j = self.c.get(self.base).json
        self.assertTrue(j["can_apply"])
        self.assertEqual(j["pieces"], [[self.s["start"], self.s["end"]]])
        self.assertTrue(all(w["kept"] for w in j["words"]))
        self.assertAlmostEqual(j["words"][0]["s"], self.s["start"] + 0.15, delta=0.5)
        self.assertEqual(self.c.get(f"/api/ai-edit/{self.jid}/99").status_code, 404)
        other = F.client(F.new_user())
        self.assertEqual(other.get(self.base).status_code, 404)  # only its owner

    def test_cut_two_parts_then_restore(self):
        s, e = self.s["start"], self.s["end"]
        keep = [[s, s + 8], [s + 12, e]]
        r = self.c.post(self.base + "/apply", json={"pieces": keep})
        self.assertEqual(r.status_code, 200, r.json)
        me = self.short()
        self.assertFalse(me.get("retry_error"), me.get("retry_error"))
        self.assertEqual(me["pieces"], keep)
        self.assertEqual(F.RENDERED[-1]["pieces"], [tuple(k) for k in keep])
        self.assertNotEqual(me["video"], self.s["video"])  # a new file, so browsers don't show the old one
        clip = next(c for c in self.c.get("/api/clips").json["items"] if c["idx"] == self.s["idx"])
        self.assertEqual(clip["length"], round(e - s - 4))
        ass = (JOBS_DIR / self.jid / me["video"].replace("short_", "captions_").replace(".mp4", ".ass")).read_text()
        last = max(ln.split(",")[2] for ln in ass.splitlines() if ln.startswith("Dialogue: 0,"))
        h, mi, sec = last.split(":")
        self.assertLessEqual(int(h) * 3600 + int(mi) * 60 + float(sec), e - s - 4 + 0.2)  # captions on the cut clock
        info = self.c.get(self.base).json
        self.assertTrue(any(not w["kept"] for w in info["words"]))
        self.assertEqual(self.c.post(self.base + "/apply", json={"pieces": keep}).json.get("unchanged"), True)
        self.c.post(self.base + "/apply", json={"pieces": None})  # the whole moment again
        self.assertIsNone(self.short().get("pieces"))

    def test_refused(self):
        s = self.s["start"]
        self.assertIn("less than", self.c.post(self.base + "/apply", json={"pieces": [[s, s + 2]]}).json["error"])
        self.assertEqual(self.c.post(self.base + "/apply", json={"pieces": "nonsense"}).status_code, 400)
        for f in (JOBS_DIR / self.jid).glob("source.*"):
            f.unlink()
        r = self.c.post(self.base + "/apply", json={"pieces": [[s, s + 20]]})
        self.assertIn("video was deleted", r.json["error"])
        self.assertFalse(self.c.get(self.base).json["can_apply"])

    def test_shorten_with_the_ai(self):
        r = self.c.post(self.base + "/suggest", json={"kind": "shorten", "target": 15})
        self.assertEqual(r.status_code, 200, r.json)
        keep = r.json["pieces"]
        total = sum(b - a for a, b in keep)
        self.assertTrue(r.json["ai"])
        self.assertTrue(12 <= total <= 19, total)
        self.assertGreater(keep[0][0], self.s["start"] + 1)  # the fake AI skips the first sentence
        self.assertIn("shorten", F.AI.kinds())
        self.assertIsNone(F.job_json(self.jid)["shorts"][0].get("pieces"))  # a suggestion saves nothing

    def test_shorten_without_the_ai(self):
        F.AI.fail(503, "overloaded", times=50)
        j = self.c.post(self.base + "/suggest", json={"kind": "shorten", "target": 15}).json
        self.assertFalse(j["ai"])
        self.assertAlmostEqual(j["pieces"][0][0], self.s["start"], delta=0.5)  # from the start, up to what fits
        self.assertLessEqual(sum(b - a for a, b in j["pieces"]), 15 * 1.25)

    def test_suggested_cuts_are_checked(self):
        cuts = self.c.post(self.base + "/suggest", json={"kind": "cuts"}).json["cuts"]
        self.assertEqual(len(cuts), 1)  # "cut everything" was refused
        self.assertEqual(cuts[0]["kind"], "repeat")
        self.assertTrue(self.s["start"] <= cuts[0]["start"] < cuts[0]["end"] <= self.s["end"])
        self.assertGreater(cuts[0]["seconds"], 1)

    def test_new_hooks_read_only_what_is_kept(self):
        s = self.s["start"]
        self.c.post(self.base + "/apply", json={"pieces": [[s, s + 10]]})
        self.short()
        F.AI.calls.clear()
        self.c.post(f"/api/hooks/{self.jid}/{self.s['idx']}", json={})
        self.assertEqual(F.AI.kinds(), ["hooks"])


if __name__ == "__main__":
    unittest.main()
