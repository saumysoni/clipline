"""Game Mode v1 (gaming.md; pipeline/game_signals.py, game_moments.py, game_check.py, game_frame.py, web/game_mode.py):
signals from generated "gameplay" (police flashing in the minimap, a WASTED screen, loud bursts), scoring that a quiet
stream can't sink, moments and montages, the AI check and its fallback, facecam and framing, and the whole run.
No real GTA footage here: the GTA V screen positions are estimates to tune on real streams."""
from tests import fakes as F

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from pipeline import game_check as GC, game_frame as GF, game_moments as GM, game_signals as GS
from pipeline.ffmpeg import ffmpeg_exe
from settings import JOBS_DIR

CACHE = Path(tempfile.gettempdir()) / f"pitcrew-test-media-{os.getuid()}"


def gameplay(seconds=120, keyint=60, name=None):
    """A plain bluish 'game' with: police red/blue flashing in the minimap 20-32 s, a grey WASTED screen with a red
    word 70-73 s, loud bursts 22-26 s and 95-99 s. keyint: frames between keyframes (60 = every 2 s at 30 fps)."""
    out = CACHE / (name or f"game_{seconds}s_k{keyint}.mp4")
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    v = ("[0:v]drawbox=x=12:y=280:w=90:h=70:color=red:t=fill:enable='between(t,20,32)*lt(mod(t,1),0.5)',"
         "drawbox=x=12:y=280:w=90:h=70:color=blue:t=fill:enable='between(t,20,32)*gte(mod(t,1),0.5)',"
         "hue=s=0:enable='between(t,70,73)',drawbox=x=220:y=160:w=200:h=40:color=red:t=fill:enable='between(t,70,73)'[v];"
         "[1:a]volume='if(between(t,22,26)+between(t,95,99),1.0,0.05)':eval=frame[a]")
    subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "color=c=0x406080:size=640x360:rate=30,noise=alls=12:allf=t,format=yuv420p",
                    "-f", "lavfi", "-i", "sine=frequency=300:sample_rate=48000", "-t", str(seconds),
                    "-filter_complex", v, "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "ultrafast",
                    "-g", str(keyint), "-c:a", "aac", str(out) + ".part.mp4"], check=True, stdin=subprocess.DEVNULL)
    os.replace(str(out) + ".part.mp4", out)
    return out


def signals_of(path, seconds=120):
    game = GS.load_game("gta5")
    pics, _ = GS.scan_pictures(path, 0, seconds, game)
    return GS.per_second(pics, GS.loudness(path, 0, seconds), {}, seconds, game), game


class Signals(unittest.TestCase):
    def test_police_wasted_and_noise_are_seen(self):
        for keyint in (60, 600):  # keyframes every 2 s (read alone), and every 20 s (one picture a second instead)
            with self.subTest(keyint=keyint):
                ps, _ = signals_of(gameplay(keyint=keyint))
                self.assertGreater(max(ps["police"][20:33]), 0.05)
                self.assertLess(max(ps["police"][45:65]), 0.05)
                self.assertEqual(max(ps["grey"][70:73]), 1.0)
                self.assertEqual(max(ps["grey"][:60]), 0.0)
                self.assertGreater(ps["loud"][24] - ps["loud"][50], 15)  # dB louder in the burst

    def test_pause_stops_the_scan_at_once(self):
        import time
        from pipeline.ffmpeg import watching
        calls = []

        def check():
            calls.append(1)
            if len(calls) > 1:
                raise InterruptedError("paused")
        t = time.time()
        with watching(check=check), self.assertRaises(InterruptedError):
            GS.scan_pictures(gameplay(keyint=600), 0, 120, GS.load_game("gta5"))
        self.assertLess(time.time() - t, 2.0)

    def test_keywords_and_games(self):
        words = [{"w": w, "s": float(k), "e": k + 0.5} for k, w in enumerate("oh my god they're here run".split())]
        self.assertEqual(GS.keyword_hits(words, ["oh my god", "run", "cops"]), {0: 1, 5: 1})
        self.assertIn("gta5", GS.games())
        with self.assertRaises(RuntimeError):
            GS.load_game("../etc/passwd")
        with self.assertRaises(RuntimeError):
            GS.load_game("valorant")


class Scoring(unittest.TestCase):
    def ps(self, n=300, **over):
        base = {"motion": [0.02] * n, "cuts": [0.0] * n, "police": [0.0] * n, "stars": [0.0] * n, "grey": [0.0] * n,
                "wred": [0.0] * n, "gold": [0.0] * n, "x": [0.5] * n, "loud": [None] * n, "keywords": [0.0] * n,
                "duration": float(n)}
        base.update(over)
        return base

    def test_a_silent_stream_still_scores_on_pictures(self):
        motion = [0.02] * 300
        for k in range(100, 115):
            motion[k] = 0.3
        s, norm = GM.score(self.ps(motion=motion), GS.load_game("gta5"))
        self.assertIsNone(norm["loud"])  # no sound: left out, not counted as zero
        self.assertGreater(s[107], 0.5)
        self.assertLess(s[200], 0.1)

    def test_wasted_is_not_the_pause_map_or_a_loading_screen(self):
        """From a real GTA Online stream: WASTED is white on grey; the pause map is grey too, but full of thin lines."""
        n, grey, edges, bright = 300, [0.0] * 300, [0.09] * 300, [0.7] * 300
        for k in range(50, 56):  # the pause map
            grey[k], edges[k] = 1.0, 0.25
        for k in range(120, 126):  # a black loading screen
            grey[k], bright[k] = 1.0, 0.05
        for k in range(200, 206):  # WASTED
            grey[k] = 1.0
        on = [k for k, x in enumerate(GM.raw_signals(self.ps(grey=grey, edges=edges, bright=bright),
                                                     GS.load_game("gta5"))["wasted"]) if x > 0]
        self.assertTrue(on and min(on) >= 188 and max(on) <= 210, on)

    def test_wanted_stars_count_only_near_the_police(self):
        stars = [0.0] * 150 + [0.2] * 150  # city lights in the corner
        game = GS.load_game("gta5")
        self.assertFalse(any(GM.raw_signals(self.ps(stars=stars), game)["stars_up"]))
        police = [0.0] * 145 + [0.1] * 20 + [0.0] * 135
        self.assertTrue(any(GM.raw_signals(self.ps(stars=stars, police=police), game)["stars_up"]))

    def test_a_moment_starts_where_whats_being_said_starts(self):
        segs = [{"s": 40.0, "e": 44.0, "text": "Whoever gets a haircut first wins."},
                {"s": 44.3, "e": 47.0, "text": "Go go go."},
                {"s": 49.5, "e": 52.5, "text": "No way, he already got one!"},
                {"s": 70.0, "e": 72.0, "text": "Later."}]
        game = GS.load_game("gta5")
        m = GM.with_context({"start": 46.0, "end": 51.0, "pieces": [[46.0, 51.0]], "score": 1,
                             "segments": [{"start": 46.0, "end": 51.0}]}, segs, game, 100)
        self.assertEqual((m["start"], m["end"], m["pieces"]), (40.0, 52.5, [[40.0, 52.5]]))  # the setup, the whole line
        far = GM.with_context({"start": 60.0, "end": 65.0, "pieces": [[60.0, 65.0]], "score": 1}, segs, game, 100)
        self.assertEqual((far["start"], far["end"]), (60.0, 65.0))  # nothing said around it: as it was

    def test_the_minimap_shows_only_while_its_there(self):
        from pipeline.game_hud import with_hud
        from web.game_mode import minimap_on
        seen = [0.0] * 10 + [1.0] * 5 + [0.0] + [1.0] * 4 + [0.0] * 5 + [1.0] + [0.0] * 10
        self.assertEqual(minimap_on({"map": seen}, {"start": 8.5, "end": 30.0}), [[10, 20]])  # a 1 s blip isn't shown
        hud = {"minimap": [0.05, 0.755, 0.19, 0.93], "on": [[10, 20]]}
        chain = with_hud("scale=1080:1920", hud, [[5.0, 12.0], [18.0, 25.0]])
        self.assertIn("enable='between(t,5.00,7.00)+between(t,7.00,9.00)'", chain)  # on the Short's clock
        self.assertEqual(with_hud("scale=1080:1920", {**hud, "on": []}, [[5.0, 12.0]]), "scale=1080:1920")

    def test_a_scoreboard_laid_over_the_video_is_found(self):
        """Pictures of random scenes; a scoreboard (fixed text-like outlines, top-right) over a third of them. Found with
        when it's on; the same pictures without it: nothing."""
        import numpy as np
        rng = np.random.default_rng(1)
        board = np.zeros((GS.H, GS.W), bool)
        for r in range(3):  # three rows of "letters"
            for c in range(12):
                board[12 + r * 16: 20 + r * 16, 250 + c * 5: 252 + c * 5] = True

        def pictures(with_board):
            lines, smalls, on = [], [], []
            for k in range(150):
                scene = rng.random((GS.H, GS.W)) < 0.12  # a busy scene's outlines
                shown = with_board and k % 3 == 0
                lines.append(np.packbits(scene | board if shown else scene))
                smalls.append(rng.random(32 * 18).astype(np.float32) * 255)
                on.append(shown)
            return lines, smalls, on
        lines, smalls, on = pictures(True)
        found = GS.find_overlays(lines, smalls, GS.load_game("gta5"))
        self.assertEqual(len(found), 1)
        x0, y0, x1, y1 = found[0]["box"]
        self.assertTrue(x0 <= 250 / GS.W < 306 / GS.W < x1 and y0 <= 12 / GS.H < 51 / GS.H < y1, found[0]["box"])
        self.assertEqual([v > 0 for v in found[0]["seen"]], on)
        self.assertEqual(GS.find_overlays(*pictures(False)[:2], GS.load_game("gta5")), [])

    def test_corner_graphics_are_laid_whole_and_smaller(self):
        from pipeline.game_hud import EXTRA_W, with_hud
        hud = {"minimap": [0.05, 0.755, 0.19, 0.93], "spot": "high", "on": [],
               "extras": [{"box": [0.775, 0.033, 0.9875, 0.367], "on": [[12, 15]]}]}
        chain = with_hud("scale=1080:1920", hud, [[10.0, 20.0]])
        self.assertIn(f"crop=iw*0.2125:ih*0.3340:iw*0.7750:ih*0.0330,scale={EXTRA_W}:-2", chain)
        self.assertIn("overlay=W-w-30:470:enable='between(t,2.00,5.00)'", chain)  # top-right, while it's on
        self.assertNotIn("0.0500", chain)  # the minimap wasn't on screen

    def test_game_shorts_show_a_wider_view(self):
        import pipeline
        rf = pipeline.clean_reframe({"layout": "fill", "moves": [], "wide": 1.0})
        self.assertEqual(rf["wide"], 1.0)
        self.assertIsNone(pipeline.clean_reframe({"layout": "fill", "moves": [], "wide": 0.5}))  # 9:16 or less = none
        self.assertEqual(GF.framing({"start": 0, "end": 10}, [0.5] * 10, {"width": 1920, "height": 1080}, None)[1]["wide"],
                         GF.WIDE)

    def test_shorts_never_repeat_a_moment(self):
        from web.game_mode import _overlaps
        montage = {"start": 10, "end": 100, "pieces": [[10, 20], [60, 70], [90, 100]]}
        self.assertTrue(_overlaps({"start": 65, "end": 80}, [montage]))
        self.assertFalse(_overlaps({"start": 30, "end": 50}, [montage]))  # in a gap between its parts

    def test_an_always_on_signal_is_ignored(self):
        _, norm = GM.score(self.ps(police=[0.2] * 300), GS.load_game("gta5"))
        self.assertIsNone(norm["chase"])

    def test_moments_are_padded_merged_and_bounded(self):
        game = GS.load_game("gta5")
        motion = [0.02] * 600
        for a, b in ((100, 110), (113, 120), (400, 460)):
            for k in range(a, b):
                motion[k] = 0.4
        s, norm = GM.score(self.ps(600, motion=motion), game)
        found = GM.candidates(s, norm, game, 600)
        c = game["clips"]
        for m in found:
            self.assertTrue(c["min"] - 0.01 <= m["end"] - m["start"] <= c["max"] + 0.01, m)
        self.assertTrue(any(m["start"] <= 97 and m["end"] >= 120 for m in found), found)  # 100-110 + 113-120 merged
        self.assertEqual(len([m for m in found if m["start"] < 150]), 1)

    def test_montages_stay_within_one_stretch(self):
        game = GS.load_game("gta5")
        motion = [0.02] * 1200
        for a in (100, 140, 180, 220, 900):  # four close together, one far away
            for k in range(a, a + 8):
                motion[k] = 0.4
        found, monts, _ = GM.plan(self.ps(1200, motion=motion), game, 5)
        self.assertEqual(len(monts), 1)
        m = monts[0]
        self.assertTrue(m["montage"] and len(m["pieces"]) >= 3)
        self.assertLessEqual(m["end"] - m["start"], game["montage"]["max_span"])
        self.assertLess(m["end"], 800)  # the far one isn't in it
        self.assertLessEqual(sum(b - a for a, b in m["pieces"]), game["montage"]["target"][1] + 0.01)
        self.assertIn("Best bits", GM.label(m))


class Check(unittest.TestCase):
    def setUp(self):
        F.install()
        F.reset()
        self.video = gameplay()
        self.cands = [{"start": 18.0, "end": 36.0, "pieces": [[18.0, 36.0]], "score": 0.8, "why": ["chase"]},
                      {"start": 60.0, "end": 80.0, "pieces": [[60.0, 80.0]], "score": 0.6, "why": ["wasted"]}]
        self.tr = F.transcript_for(120)

    def test_the_ai_names_and_ranks_them(self):
        got = GC.check(self.video, self.cands, self.tr, "GTA V")
        self.assertEqual(F.AI.kinds(), ["game"])
        self.assertEqual(len(got), 1)  # the fake turns the last one down
        self.assertEqual((got[0]["title"], got[0]["hook"], got[0]["ai"]), ("Chase 1 goes wrong", "No way out", True))

    def test_no_ai_means_the_detectors_order(self):
        F.AI.fail(500, "unavailable", times=50)
        got = GC.check(self.video, self.cands, self.tr, "GTA V")
        self.assertEqual([m["start"] for m in got], [18.0, 60.0])
        self.assertFalse(got[0]["ai"])
        self.assertEqual(got[1]["title"], "Wasted")

    def test_pictures_are_the_middle_third(self):
        pics = GC.frames(self.video, {"start": 10, "end": 20, "pieces": [[10, 12], [50, 58]]})
        self.assertEqual(len(pics), GC.CHECK_FRAMES)
        import cv2
        import numpy as np
        h, w = cv2.imdecode(np.frombuffer(pics[0], np.uint8), cv2.IMREAD_COLOR).shape[:2]
        self.assertEqual(h, 480)
        self.assertAlmostEqual(w, 480 * 16 / 9 / 3, delta=4)


class Framing(unittest.TestCase):
    def test_facecam_is_a_face_that_stays_in_a_corner(self):
        cam = (0.88, 0.85, 0.06, 0.1)
        looks = [[cam] for _ in range(8)] + [[(0.5, 0.4, 0.05, 0.08)], None, [], [(0.5, 0.5, 0.4, 0.5)]]
        box = GF.facecam_spot(looks)
        self.assertTrue(box and box["x0"] < 0.88 < box["x1"] and box["y0"] < 0.85 < box["y1"])
        self.assertIsNone(GF.facecam_spot([[(0.1 * k, 0.5, 0.05, 0.08)] for k in range(8)]))  # never the same spot
        self.assertIsNone(GF.facecam_spot([[(0.5, 0.5, 0.4, 0.5)]] * 8))  # a cutscene face filling the screen

    def test_the_frame_changes_through_the_short(self):
        """An edited compilation: a streamer on the right, a cut to gameplay with nobody, a cut to a streamer beside
        their character (too far apart for one 9:16 frame: shown whole), then the streamer walks left."""
        cam = (0.75, 0.5, 0.1, 0.2)
        looks = ([(t / 2, [cam]) for t in range(0, 10)]                                   # 0-5 s
                 + [(t / 2, []) for t in range(10, 20)]                                   # 5-10 s
                 + [(t / 2, [(0.25, 0.5, 0.1, 0.2), cam]) for t in range(20, 30)]         # 10-15 s
                 + [(t / 2, [cam]) for t in range(30, 34)] + [(t / 2, [(0.3, 0.5, 0.1, 0.2)]) for t in range(34, 40)])
        xs = [0.5] * 5 + [0.2] * 5 + [0.5] * 10
        rf = GF.shot_plan(looks, [0.0, 5.0, 10.0, 15.0], 20.0, xs, 0.316)
        self.assertEqual([s["fit"] for s in rf["shots"]], [False, False, True, False])
        at = {m["t"]: m for m in rf["moves"]}
        self.assertAlmostEqual(at[0.0]["x"], 0.75)
        self.assertAlmostEqual(at[5.0]["x"], 0.2)   # nobody: the motion
        self.assertAlmostEqual(rf["moves"][-1]["x"], 0.3)  # followed the streamer inside the shot
        self.assertFalse(rf["moves"][-1].get("jump"))    # a glide, not a cut
        self.assertEqual(GF.shot_plan([], [0.0], 10.0, [0.6] * 10, 0.316)["moves"][0]["x"], 0.6)
        import pipeline
        self.assertEqual(pipeline.clean_reframe(rf)["shots"][2], {"t": 10.0, "fit": True})

    def test_split_with_a_facecam_else_a_frame_per_part(self):
        meta = {"width": 1920, "height": 1080}
        xs = [0.3] * 50 + [0.8] * 50
        m = {"start": 10, "end": 70, "pieces": [[10, 20], [60, 70]]}
        cx, rf = GF.framing(m, xs, meta, None)
        self.assertEqual(rf["layout"], "fill")
        self.assertEqual([(mv["t"], mv["x"]) for mv in rf["moves"]], [(10, 0.3), (60, 0.8)])
        self.assertAlmostEqual(cx, 0.3 * 1920)
        cx, rf = GF.framing(m, xs, meta, {"x0": 0.78, "y0": 0.7, "x1": 0.98, "y1": 0.98})
        self.assertEqual(rf["layout"], "split")
        self.assertAlmostEqual(rf["bottom"]["x"], 0.88)
        self.assertLessEqual(rf["bottom"]["z"], 2.5)
        import pipeline
        self.assertEqual(pipeline.clean_reframe(rf)["layout"], "split")  # what the editor's Reframe reads


class Run(unittest.TestCase):
    def setUp(self):
        F.install()
        F.reset()
        self.c = F.client(F.new_user())

    def start(self, **form):
        up = F.upload(self.c, gameplay())
        return self.c.post("/api/start", data={"count": "3", "upload": up, "game": "gta5", **form})

    def test_a_gameplay_stream_becomes_shorts(self):
        r = self.start()
        self.assertEqual(r.status_code, 200, r.json)
        st = F.wait_ready(self.c, r.json["id"], timeout=120)
        self.assertEqual(st["status"], "ready", st.get("error"))
        self.assertTrue(st["shorts"])
        job = F.job_json(r.json["id"])
        self.assertEqual(job["game"], "gta5")
        self.assertNotIn("little_speech", job)  # quiet gameplay isn't "little speech"
        self.assertIn("game", F.AI.kinds())
        self.assertNotIn("moments", F.AI.kinds())  # the transcript picker isn't asked
        for s in st["shorts"]:
            self.assertEqual(s["game"]["game"], "gta5")
            self.assertIn(s["reframe"]["layout"], ("fill", "split"))
            self.assertIsInstance(s["cx"], (int, float))
        self.assertTrue((JOBS_DIR / r.json["id"] / "game_signals.json").exists())  # Resume won't read it all again
        windows = [(s["start"], s["end"]) for s in st["shorts"] if not s["game"]["montage"]]
        self.assertTrue(any(a <= 30 and b >= 22 for a, b in windows), windows)  # the chase + noise
        self.assertTrue(any(a <= 72 and b >= 70 for a, b in windows), windows)  # WASTED
        cost = job["game_ai"]  # what the AI check cost, per vlog
        self.assertEqual((cost["provider"], cost["moments"] > 0), ("gemini", True))
        self.assertEqual(cost["pictures"], cost["moments"] * GC.CHECK_FRAMES)
        self.assertGreater(cost["input_tokens"], 0)
        self.assertGreater(cost["output_tokens"], 0)
        self.turned_down(r.json["id"], st["shorts"])

    def turned_down(self, jid, shorts):
        """A deleted draft and a Short replaced by Try again are logged with what the detector saw; kept ones aren't."""
        from web.game_feedback import game_verdicts
        gone, again = shorts[0], shorts[1]
        r = self.c.post("/api/clips/delete", json={"items": [{"job": jid, "idx": gone["idx"]}]})
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual(self.c.post(f"/api/retry/{jid}/{again['idx']}", json={}).status_code, 200)
        import time
        for _ in range(300):  # Try again runs behind the button
            job = F.job_json(jid)
            me = next(s for s in job["shorts"] if s["idx"] == again["idx"])
            if not me.get("retrying"):
                break
            time.sleep(0.1)
        self.assertFalse(me.get("retry_error"), me.get("retry_error"))
        self.assertNotIn("game", me)  # Try again picked from the transcript: no longer a game moment
        log = job["game_log"]
        self.assertEqual([e["verdict"] for e in log], ["deleted", "tried_again"])
        self.assertEqual((log[0]["start"], log[0]["label"]), (gone["start"], gone["game"]["label"]))
        self.assertEqual(log[1]["signals"], again["game"]["signals"])
        verdicts = game_verdicts(job)
        self.assertEqual(sorted(v["verdict"] for v in verdicts),
                         sorted(["deleted", "tried_again"] + ["draft"] * (len(shorts) - 2)))

    def test_resume_reuses_the_signals(self):
        import pipeline
        from unittest import mock
        from web import game_mode
        jid = "abcdef1234"
        (JOBS_DIR / jid).mkdir(parents=True, exist_ok=True)
        run = type("R", (), {"doing": staticmethod(lambda fn, *a, **k: fn(*a, **k))})()
        video, game = gameplay(), GS.load_game("gta5")
        meta, tr, steps = {"duration": 120.0, "width": 640, "height": 360}, F.transcript_for(120), []
        first = game_mode.signals(jid, video, meta, tr, game, run, lambda **k: steps.append(k))
        self.assertTrue(any("Watching the gameplay" in k.get("msg", "") for k in steps))
        with mock.patch.object(pipeline, "game_scan", side_effect=AssertionError("read again")):
            again = game_mode.signals(jid, video, meta, tr, game, run, lambda **k: None)
        self.assertEqual(again["police"], first["police"])

    def test_unknown_game_is_refused(self):
        r = self.start(game="minecraft")
        self.assertEqual((r.status_code, r.json["field"]), (400, "game"))


if __name__ == "__main__":
    unittest.main()
