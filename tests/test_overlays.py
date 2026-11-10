"""Text & Overlays (pipeline/overlays.py, web/overlays.py): a Short's text on screen, cleaned; the .ass lines it makes
(nothing at all without it, so the captions' golden file holds); its times through cuts; shown with captions off; saving
with and without a remake; other remakes keeping it, Try again dropping it; the preview taking text not saved yet."""
from tests import fakes as F

import tempfile
import unittest
from pathlib import Path

from pipeline import captions as C
from pipeline import overlays as O
from settings import JOBS_DIR


def one(**k):
    return {"id": "a1", "text": "Day 3 in Goa", "a": 12.0, "b": 15.0, **k}


def ass(overlays, pieces=((10.0, 40.0),), caps=None):
    d = Path(tempfile.mkdtemp())
    words = [{"w": "hello", "s": 0.5, "e": 0.9, "i": 0}]
    C.build_ass(words, 0.0, 30.0, "", "bold", d / "c.ass", caps, overlays=O.clean_overlays(overlays, 100), pieces=list(pieces))
    return (d / "c.ass").read_text(encoding="utf-8")


def events(text):
    return [line for line in text.splitlines() if line.startswith("Dialogue: 2,")]


class Clean(unittest.TestCase):
    def test_defaults_and_limits(self):
        self.assertIsNone(O.clean_overlays(None))
        self.assertIsNone(O.clean_overlays([{"text": "  "}, "x", {"text": "no time"}]))
        o = O.clean_overlays([{"text": " Hi \n\n  there \n a\nb", "a": 5, "b": 99, "x": 2, "y": -1, "style": "weird",
                               "font": "comic", "color": "red", "size": "xl", "anim": "spin", "id": "bad id!"}], duration=50)[0]
        self.assertEqual(o["text"], "Hi\nthere\na")  # 3 lines at most, spaces tidied
        self.assertEqual((o["a"], o["b"]), (5.0, 50.0))  # not past the vlog's end
        self.assertEqual((o["x"], o["y"]), (1 - O.EDGE, O.EDGE))
        self.assertEqual((o["style"], o["font"], o["color"], o["size"], o["anim"], o["id"]),
                         ("bold", "default", "#FFFFFF", "m", "none", "t0"))
        self.assertEqual(O.clean_overlays([one(b=12.1)])[0]["b"], 12.3)  # on screen at least MIN_LEN
        self.assertEqual(O.clean_overlays([one(b=500)])[0]["b"], 12 + O.MAX_LEN)
        self.assertEqual(len(O.clean_overlays([one(id=f"i{k}") for k in range(10)])), O.MAX)
        ids = [x["id"] for x in O.clean_overlays([one(), one(), one()])]
        self.assertEqual(len(set(ids)), 3)  # the same id twice: made unique
        self.assertEqual(O.clean_overlays([one(text="x" * 500)])[0]["text"], "x" * O.MAX_TEXT)

    def test_times_through_cuts(self):
        self.assertEqual(O.on_short([(10, 20)], 12, 15), [(2, 5)])
        # across a cut: in both parts; all of it cut: nowhere
        self.assertEqual(O.on_short([(10, 14), (30, 40)], 12, 32), [(2, 4), (4, 6)])
        self.assertEqual(O.on_short([(10, 14), (30, 40)], 20, 25), [])


class Build(unittest.TestCase):
    def test_nothing_without_overlays(self):
        plain = ass(None)
        self.assertNotIn("Ovl", plain)
        self.assertEqual(plain, ass([]))
        self.assertEqual(plain, ass([{"text": ""}]))

    def test_lines(self):
        text = ass([one(x=0.5, y=0.25, color="#FFD60A", line="#112233", size="l", font="anton", anim="pop")])
        self.assertIn("Style: Ovl,", text)
        self.assertIn("Style: OvlBox,", text)
        (ev,) = events(text)
        self.assertTrue(ev.startswith("Dialogue: 2,0:00:02.00,0:00:05.00,Ovl,"), ev)
        self.assertIn("\\an5\\pos(540,480)", ev)
        self.assertIn("\\fnAnton", ev)
        self.assertIn("\\fs136", ev)
        self.assertIn("\\c&H0AD6FF&", ev)   # blue, green, red
        self.assertIn("\\3c&H332211&", ev)
        self.assertIn("\\fscx40", ev)      # pops in
        self.assertTrue(ev.endswith("}Day 3 in Goa"))
        boxed = events(ass([one(style="boxed", text="Two\nlines {x}")]))[0]
        self.assertIn(",OvlBox,", boxed)
        self.assertTrue(boxed.endswith("}Two\\Nlines (x)"))  # a new line, and braces can't become tags
        self.assertIn("\\1a&HFF&", events(ass([one(style="hollow")]))[0])
        self.assertIn("\\move(540,656,540,576,0,220)", events(ass([one(anim="slide")]))[0])

    def test_across_a_cut_and_with_captions_off(self):
        evs = events(ass([one(a=12, b=32, anim="fade")], pieces=[(10, 14), (30, 40)]))
        self.assertEqual(len(evs), 2)
        self.assertIn("\\fad(", evs[0])
        self.assertNotIn("\\fad(", evs[1])  # comes in once, at its start
        off = ass([one()], caps={**C.preset("bold"), "on": False})
        self.assertEqual(len(events(off)), 1)
        self.assertNotIn("Dialogue: 0,", off)  # no captions, the text stays


class Routes(unittest.TestCase):
    def setUp(self):
        F.install()
        F.reset()
        self.u = F.new_user()
        self.c = F.client(self.u)
        self.jid, st = F.make_shorts(self.c, 150, 2)
        self.s = st["shorts"][0]
        self.base = f"/api/overlays/{self.jid}/{self.s['idx']}"
        self.text = one(a=self.s["start"] + 1, b=self.s["start"] + 4)

    def short(self):
        return F.wait(lambda: (x := next(y for y in F.job_json(self.jid)["shorts"] if y["idx"] == self.s["idx"]))
                      and not x.get("retrying") and x, what="remade")

    def ass_of(self, me):
        return (JOBS_DIR / self.jid / me["video"].replace("short_", "captions_").replace(".mp4", ".ass")).read_text()

    def test_info(self):
        j = self.c.get(self.base).json
        self.assertEqual((j["overlays"], j["max"], j["can_apply"]), ([], O.MAX, True))
        self.assertEqual([x["id"] for x in j["styles"]], list(O.STYLES))
        self.assertIn("bangers", [f["id"] for f in j["fonts"]])
        self.assertEqual(F.client(F.new_user()).get(self.base).status_code, 404)  # only its owner

    def test_save_and_remake(self):
        r = self.c.post(self.base, json={"overlays": [self.text], "remake": True})
        self.assertEqual(r.status_code, 200, r.json)
        me = self.short()
        self.assertFalse(me.get("retry_error"), me.get("retry_error"))
        self.assertNotEqual(me["video"], self.s["video"])
        self.assertEqual(me["overlays"][0]["text"], "Day 3 in Goa")
        self.assertEqual(len(events(self.ass_of(me))), 1)
        self.assertEqual(self.c.get(self.base).json["overlays"][0]["id"], "a1")
        # taken off again
        self.c.post(self.base, json={"overlays": [], "remake": True})
        me = self.short()
        self.assertIsNone(me["overlays"])
        self.assertEqual(events(self.ass_of(me)), [])

    def test_other_remakes_keep_it_try_again_drops_it(self):
        video = self.s["video"]
        self.assertEqual(self.c.post(self.base, json={"overlays": [self.text], "remake": False}).status_code, 200)
        self.assertEqual(self.short()["video"], video)  # saved, not remade
        self.c.post(f"/api/hook/{self.jid}/{self.s['idx']}", json={"mode": "text", "text": "Wait for it"})
        me = self.short()
        self.assertEqual(F.RENDERED[-1]["overlays"][0]["id"], "a1")
        self.assertEqual(len(events(self.ass_of(me))), 1)
        self.c.post(f"/api/captions/{self.jid}/{self.s['idx']}", json={"captions": C.preset("pop"), "remake": True})
        self.short()
        self.assertEqual(F.RENDERED[-1]["overlays"][0]["id"], "a1")
        self.assertEqual(self.c.post(f"/api/retry/{self.jid}/{self.s['idx']}", json={}).status_code, 200)
        me = self.short()
        self.assertFalse(me.get("retry_error"), me.get("retry_error"))
        self.assertIsNone(me.get("overlays"))  # a new moment: the text was on the old one's times

    def test_refused(self):
        self.assertEqual(self.c.post(self.base, json={"overlays": "nope"}).status_code, 400)
        from web.store import update_short
        update_short(self.jid, self.s["idx"], retrying=True)
        self.assertIn("still being made", self.c.post(self.base, json={"overlays": []}).json["error"])
        update_short(self.jid, self.s["idx"], retrying=False)
        for f in (JOBS_DIR / self.jid).glob("source.*"):
            f.unlink()
        r = self.c.post(self.base, json={"overlays": [self.text], "remake": True})
        self.assertIn("text on it can't be changed", r.json["error"])
        self.assertFalse(self.c.get(self.base).json["can_apply"])

    def test_preview_takes_text_not_saved_yet(self):
        import pipeline
        seen = {}

        def frame(src, meta, moment, words, at, style, job_dir, caps=None, offset=0.0):
            seen.update(moment=moment)
            return b"\xff\xd8jpeg"
        real, pipeline.caption_frame = pipeline.caption_frame, frame
        try:
            r = self.c.post(f"/api/captions/{self.jid}/{self.s['idx']}/preview",
                            json={"at": self.s["start"] + 2, "overlays": [self.text, {"text": ""}]})
            self.assertEqual(r.status_code, 200)
            self.assertEqual([x["id"] for x in seen["moment"]["overlays"]], ["a1"])
        finally:
            pipeline.caption_frame = real


if __name__ == "__main__":
    unittest.main()
