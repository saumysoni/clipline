"""Reframe (pipeline/smart_reframe.py, web/reframe.py): a Short's own framing, cleaned; no framing = exactly the crop
around the face it always had; where the frame is over time (holds, glides, cuts, across cuts in the Short); the filters
for Fill, Fit and Split and the moving frame's command file; saving with and without a remake; other remakes keeping
it, Try again keeping only the layout; Follow the speaker's moves. The real FFmpeg runs in tests/system."""
from tests import fakes as F

import tempfile
import unittest
from pathlib import Path

from pipeline import smart_reframe as R
from pipeline.reframe import crop_filter

META = {"width": 1920, "height": 1080}


class Framing(unittest.TestCase):
    def test_none_is_the_old_crop_exactly(self):
        d = tempfile.mkdtemp()
        for cx in (None, 400, 1700):
            for rf in (None, {}, {"layout": "fill"}, {"layout": "fill", "moves": []}, "nope"):
                self.assertEqual(R.reframe_filter(META, cx, rf, [(10, 20)], d), (crop_filter(META, cx), None))
        # an already vertical vlog: padded as before, whatever was asked
        tall = {"width": 1080, "height": 1920}
        self.assertEqual(R.reframe_filter(tall, None, {"layout": "split"}, [(0, 5)], d)[0], crop_filter(tall, None))
        self.assertEqual(list(Path(d).iterdir()), [])

    def test_clean(self):
        self.assertIsNone(R.clean_reframe(None))
        self.assertIsNone(R.clean_reframe({"layout": "fill", "moves": "x"}))
        r = R.clean_reframe({"layout": "weird", "cut": 1, "moves": [
            {"t": 12, "x": 2, "y": -1, "z": 9}, {"t": 3, "x": 0.25}, {"t": 3, "x": 0.4}, {"t": "soon"}, "x", {"t": 500}]},
            duration=100)
        self.assertEqual(r["layout"], "fill")
        self.assertTrue(r["cut"])
        self.assertEqual(r["moves"], [{"t": 3.0, "x": 0.4, "y": 0.5, "z": 1.0}, {"t": 12.0, "x": 1.0, "y": 0.0, "z": R.ZOOM_MAX},
                                      {"t": 100.0, "x": 0.5, "y": 0.5, "z": 1.0}])
        r = R.clean_reframe({"layout": "split", "top": {"x": 0.1}, "moves": [{"t": i} for i in range(300)]})
        self.assertEqual((r["top"], r["bottom"], len(r["moves"])), ({"x": 0.1, "y": 0.5, "z": 1.0}, R.SPLIT_BOTTOM, R.MAX_MOVES))
        self.assertEqual(R.clean_reframe({"layout": "fit"}), {"layout": "fit", "moves": [], "cut": False})
        self.assertEqual(R.reframe_style_only({"layout": "split", "moves": [{"t": 3}]})["moves"], [])
        self.assertIsNone(R.reframe_style_only({"moves": [{"t": 3, "x": 0.2}]}))

    def test_where_the_frame_is(self):
        m = [{"t": 10, "x": 0.2, "y": 0.5, "z": 1}, {"t": 20, "x": 0.8, "y": 0.5, "z": 2}]
        self.assertEqual(R.framing_at(m, 0), (0.2, 0.5, 1))       # before the first move: its place
        self.assertEqual(R.framing_at(m, 19.3), (0.2, 0.5, 1))    # holds until the glide
        mid = R.framing_at(m, 20 - R.GLIDE / 2)
        self.assertAlmostEqual(mid[0], 0.5, 3)                    # half way, eased
        self.assertAlmostEqual(mid[2], 1.5, 3)
        self.assertEqual(R.framing_at(m, 20), (0.8, 0.5, 2))
        self.assertEqual(R.framing_at(m, 99), (0.8, 0.5, 2))
        self.assertEqual(R.framing_at(m, 19.9, cut=True), (0.2, 0.5, 1))  # cut: jumps at the move's time
        self.assertEqual(R.to_vlog([(10, 15), (30, 40)], 7), 32)
        self.assertEqual(R.window(META, 0.0, 0.5, 1), (0, 0, 607.5, 1080))  # kept inside the picture
        left, top, cw, ch = R.window(META, 0.5, 0.9, 2)
        self.assertEqual((cw, ch, top), (303.75, 540, 540))

    def test_filters(self):
        d = Path(tempfile.mkdtemp())
        one = R.reframe_filter(META, None, {"moves": [{"t": 3, "x": 0, "z": 2}]}, [(0, 9)], d)
        self.assertEqual(one, ("crop=304:540:0:270,scale=1080:1920:flags=lanczos", None))
        fit, _ = R.reframe_filter(META, None, {"layout": "fit"}, [(0, 9)], d)
        self.assertIn("overlay=(W-w)/2:(H-h)/2", fit)
        split, _ = R.reframe_filter(META, None, {"layout": "split"}, [(0, 9)], d)
        self.assertIn("scale=1080:960", split)
        self.assertIn("vstack", split)
        # pan only: one crop moved along; the file says where, on the Short's clock (the pieces joined)
        f, name = R.reframe_filter(META, None, {"moves": [{"t": 10, "x": 0.2}, {"t": 32, "x": 0.8}]}, [(10, 15), (30, 40)], d)
        self.assertTrue(f.startswith(f"sendcmd=f={name},crop@rfa=608:1080:0:0,scale=1080:1920"))
        lines = (d / name).read_text().splitlines()
        self.assertTrue(lines[0].startswith("0.0000 [enter] crop@rfa x 80,"))
        last = lines[-1]
        self.assertIn(f"crop@rfa x {R._even(0.8 * 1920 - 304)}", last)
        t_last = float(last.split()[0])
        self.assertTrue(5 + 2 - R.GLIDE - 0.05 <= t_last <= 7.05, t_last)  # arrives by 32 s of the vlog = 7 s in
        # a zoom: a fixed crop, a scale and a crop again
        f, name = R.reframe_filter(META, None, {"moves": [{"t": 0, "z": 1}, {"t": 2, "z": 2}]}, [(0, 4)], d)
        self.assertIn("scale@rfz=", f)
        self.assertIn("crop@rf=1080:1920", f)
        self.assertIn("scale@rfz w 2162, [enter] scale@rfz h 3840, [enter] crop@rf x 540, [enter] crop@rf y 960", (d / name).read_text().splitlines()[-1])
        R.drop_commands(d, name)
        self.assertFalse((d / name).exists())

    def test_zoom_commands_fit_any_size(self):
        """Every line: the crop is inside the scaled picture (rounding left 640x360 and 1280x720 2 px short once)."""
        moves = [{"t": 0, "z": 1}, {"t": 2, "x": 0.9, "z": 2.5}, {"t": 4, "x": 0.1, "y": 0.9, "z": 1.3}]
        for w, h in [(640, 360), (1280, 720), (1920, 1080), (3840, 2160), (1440, 1080), (720, 480), (854, 480)]:
            d = Path(tempfile.mkdtemp())
            _, name = R.reframe_filter({"width": w, "height": h}, None, {"moves": moves}, [(0, 6)], d)
            for ln in (d / name).read_text().splitlines():
                v = {}
                for q in ln.split(" ", 1)[1].rstrip(";").split(","):
                    a, b, c = q.replace("[enter]", "").split()
                    v[a + b] = int(c)
                self.assertTrue(0 <= v["crop@rfx"] <= v["scale@rfzw"] - 1080 and 0 <= v["crop@rfy"] <= v["scale@rfzh"] - 1920,
                                (w, h, ln))


class Smart(unittest.TestCase):
    def test_shots_punch_jump_cleaned(self):
        r = R.clean_reframe({"moves": [{"t": 1, "x": 0.2, "jump": 1}, {"t": 5, "x": 0.8}],
                             "shots": [{"t": 4, "fit": 1}, {"t": 1}, "x", {"t": "soon"}], "punch": {"amount": 9, "at": [3, 1, 1, "x"]}})
        self.assertEqual(r["moves"][0]["jump"], True)
        self.assertNotIn("jump", r["moves"][1])
        self.assertEqual(r["shots"], [{"t": 1.0, "fit": False}, {"t": 4.0, "fit": True}])
        self.assertEqual(r["punch"], {"amount": R.PUNCH_MAX, "at": [1.0, 3.0]})
        self.assertNotIn("shots", R.clean_reframe({"moves": [{"t": 1}], "shots": [{"t": 1, "fit": False}]}))  # no Fit: no shots
        self.assertIsNotNone(R.clean_reframe({"shots": [{"t": 1, "fit": True}]}))  # Fit shots alone are settings
        self.assertIsNone(R.clean_reframe({"punch": {"amount": 0.1, "at": []}}))
        tried = R.reframe_style_only(r)
        self.assertIsNone(tried)  # Try again: the shots, punch-ins and moves were on the old moment's times

    def test_jump_punch_fit_over_time(self):
        m = [{"t": 0, "x": 0.2, "y": 0.5, "z": 1}, {"t": 4, "x": 0.8, "y": 0.5, "z": 1, "jump": True}]
        self.assertEqual(R.framing_at(m, 3.9), (0.2, 0.5, 1))  # no glide to a jump
        self.assertEqual(R.framing_at(m, 4), (0.8, 0.5, 1))
        p = {"amount": 0.2, "at": [2, 5, 7]}
        self.assertEqual([R.punch_at(p, t) for t in (1, 2, 4, 5, 6, 8)], [1, 1.2, 1.2, 1, 1, 1.2])
        shots = [{"t": 10, "fit": False}, {"t": 13, "fit": True}, {"t": 16, "fit": False}]
        self.assertTrue(R.fit_at(shots, 14) and not R.fit_at(shots, 12) and not R.fit_at(shots, 17))
        # on the Short's clock: pieces 10-14 and 15-20 -> Fit from 3 s in (vlog 13) to 4 s (the cut), then 4-5 (vlog 15-16)
        self.assertEqual(R.fit_ranges(shots, [(10, 14), (15, 20)]), [(3.0, 5.0)])

    def test_fill_with_fit_shots_and_punch(self):
        d = Path(tempfile.mkdtemp())
        f, name = R.reframe_filter(META, 960, {"shots": [{"t": 0, "fit": False}, {"t": 3, "fit": True}],
                                              "punch": {"amount": 0.2, "at": [1, 2]}}, [(0, 6)], d)
        self.assertTrue(f.startswith("split[rfm][rfn];[rfm]sendcmd=f=" + name))
        self.assertIn("overlay=enable='between(t,3.000,6.000)'", f)
        self.assertIn("scale@rfz", f)  # a punch-in zooms
        lines = (d / name).read_text().splitlines()
        sizes = {int(ln.split("scale@rfz w ")[1].split(",")[0]) for ln in lines}
        self.assertEqual(len(sizes), 2)  # in and out
        f2, n2 = R.reframe_filter(META, 960, {"shots": [{"t": 0, "fit": True}]}, [(0, 6)], d)
        self.assertIn("between(t,0.000,6.000)", f2)
        self.assertIsNone(n2)  # the frame doesn't move: no command file


class Routes(unittest.TestCase):
    def setUp(self):
        F.install()
        F.reset()
        self.c = F.client(F.new_user())
        self.jid, st = F.make_shorts(self.c, 150, 2)
        self.s = st["shorts"][0]
        self.base = f"/api/reframe/{self.jid}/{self.s['idx']}"

    def short(self):
        return F.wait(lambda: (x := next(y for y in F.job_json(self.jid)["shorts"] if y["idx"] == self.s["idx"]))
                      and not x.get("retrying") and x, what="remade")

    def test_info_save_remake(self):
        j = self.c.get(self.base).json
        self.assertTrue(j["can_apply"])
        self.assertIsNone(j["reframe"])
        self.assertEqual(j["vertical"], False)
        from web.reframe import _zoom_max
        self.assertEqual((_zoom_max(360), _zoom_max(720), _zoom_max(1080), _zoom_max(2160)), (1.25, 1.67, R.ZOOM_MAX, R.ZOOM_MAX))
        self.assertEqual(F.client(F.new_user()).get(self.base).status_code, 404)  # only its owner
        s = self.s["start"]
        rf = {"layout": "fill", "moves": [{"t": s, "x": 0.3}, {"t": s + 4, "x": 0.7, "z": 1.5}]}
        self.assertEqual(self.c.post(self.base, json={"reframe": rf, "remake": True}).status_code, 200)
        me = self.short()
        self.assertFalse(me.get("retry_error"), me.get("retry_error"))
        self.assertNotEqual(me["video"], self.s["video"])
        self.assertEqual(F.RENDERED[-1]["reframe"]["moves"][1]["z"], 1.5)
        self.assertEqual(self.c.get(self.base).json["reframe"]["moves"][0]["x"], 0.3)
        # back to the default
        self.c.post(self.base, json={"reframe": None, "remake": False})
        self.assertIsNone(self.short().get("reframe"))

    def test_other_remakes_keep_it_try_again_keeps_the_layout(self):
        s = self.s["start"]
        self.c.post(self.base, json={"reframe": {"layout": "split", "top": {"x": 0.2}, "moves": [{"t": s}]}, "remake": False})
        self.c.post(f"/api/hook/{self.jid}/{self.s['idx']}", json={"mode": "text", "text": "Wait for it"})
        self.short()
        self.assertEqual(F.RENDERED[-1]["reframe"]["top"]["x"], 0.2)
        self.c.post(f"/api/captions/{self.jid}/{self.s['idx']}", json={"captions": {}, "remake": True})
        self.short()
        self.assertEqual(F.RENDERED[-1]["reframe"]["layout"], "split")
        self.assertEqual(self.c.post(f"/api/retry/{self.jid}/{self.s['idx']}", json={}).status_code, 200)
        me = self.short()
        self.assertFalse(me.get("retry_error"), me.get("retry_error"))
        self.assertEqual((me["reframe"]["layout"], me["reframe"]["top"]["x"], me["reframe"]["moves"]), ("split", 0.2, []))

    def test_follow_and_preview_get_it(self):
        import pipeline
        seen = {}

        def follow(src, meta, pieces, z=1.0, offset=0.0):
            seen.update(pieces=pieces, z=z)
            return [{"t": pieces[0][0], "x": 0.4, "y": 0.5, "z": z}]

        def frame(src, meta, moment, words, at, style, job_dir, caps=None, offset=0.0):
            seen.update(moment=moment)
            return b"\xff\xd8jpeg"
        real = pipeline.follow_moves, pipeline.caption_frame
        pipeline.follow_moves, pipeline.caption_frame = follow, frame
        try:
            s = self.s["start"]
            j = self.c.post(self.base + "/follow", json={"pieces": [[s, s + 5], [s + 8, s + 20]], "z": 9}).json
            self.assertEqual((j["moves"][0]["x"], seen["z"], seen["pieces"]), (0.4, R.ZOOM_MAX, [(s, s + 5), (s + 8, s + 20)]))
            pipeline.follow_moves = lambda *a, **k: []
            self.assertIn("No face", self.c.post(self.base + "/follow", json={}).json["note"])
            r = self.c.post(f"/api/captions/{self.jid}/{self.s['idx']}/preview", json={"reframe": {"layout": "fit"}})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(seen["moment"]["reframe"]["layout"], "fit")
        finally:
            pipeline.follow_moves, pipeline.caption_frame = real

    def test_auto_and_track_routes(self):
        import pipeline
        seen = {}

        def auto(src, meta, pieces, offset=0.0):
            seen.update(auto=pieces)
            return {"shots": [{"t": pieces[0][0], "fit": True}], "moves": []}

        def track(src, meta, pieces, at, x, y, z=1.0, offset=0.0):
            seen.update(track=(at, x, y, z))
            return [{"t": at, "x": x, "y": 0.5, "z": z}, {"t": at + 1, "x": x + 0.1, "y": 0.5, "z": z}], at + 1
        real = pipeline.auto_shots, pipeline.track_moves
        pipeline.auto_shots, pipeline.track_moves = auto, track
        try:
            s = self.s["start"]
            j = self.c.post(self.base + "/auto", json={"pieces": [[s, s + 6]]}).json
            self.assertEqual((j["shots"][0]["fit"], seen["auto"]), (True, [(s, s + 6)]))
            j = self.c.post(self.base + "/track", json={"at": s + 2, "x": 1.5, "y": 0.3, "z": 9}).json
            self.assertEqual((len(j["moves"]), j["until"], seen["track"]), (2, s + 3, (s + 2, 1, 0.3, R.ZOOM_MAX)))
            self.assertEqual(self.c.post(self.base + "/track", json={"x": 1}).status_code, 400)
            pipeline.track_moves = lambda *a, **k: ([], 0)
            self.assertIn("couldn't follow", self.c.post(self.base + "/track", json={"at": s, "x": 0.5, "y": 0.5}).json["note"])
            pipeline.auto_shots = lambda *a, **k: {}
            self.assertIn("couldn't read the shots", self.c.post(self.base + "/auto", json={}).json["note"])
        finally:
            pipeline.auto_shots, pipeline.track_moves = real

    def test_refused(self):
        self.assertEqual(self.c.post(self.base, json={"reframe": "nope"}).status_code, 400)
        from settings import JOBS_DIR
        for f in (JOBS_DIR / self.jid).glob("source.*"):
            f.unlink()
        r = self.c.post(self.base, json={"reframe": {"layout": "fit"}, "remake": True})
        self.assertIn("framing can't be changed", r.json["error"])
        self.assertFalse(self.c.get(self.base).json["can_apply"])
        self.assertEqual(self.c.post(self.base + "/follow", json={}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
