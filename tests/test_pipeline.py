"""The editing rules that decide what a Short looks like: moments, captions, crop, hooks, transcripts."""
from tests import _env  # noqa: F401  (first: throwaway folders)

import re
import tempfile
import unittest
from pathlib import Path

from pipeline.captions import build_ass
from pipeline.constants import MAX_LEN, MIN_LEN
from pipeline.hooks import hook_fields
from pipeline.moments import clean_moments
from pipeline.reframe import crop_filter
from pipeline.text import without_emoji
from pipeline.transcribe import drop_repeats


def words_every(step, until, start=0.0):
    """A transcript with one word every `step` seconds."""
    out, t, k = [], start, 0
    while t + step <= until:
        out.append({"w": f"w{k}", "s": round(t, 2), "e": round(t + step * 0.8, 2)})
        t += step
        k += 1
    return out


class CleanMoments(unittest.TestCase):
    def setUp(self):
        self.tr = {"words": words_every(0.5, 600), "duration": 600}

    def test_snaps_to_words_and_keeps_length(self):
        got = clean_moments([{"start": 10.1, "end": 40.3, "title": "A"}], self.tr, 1)
        self.assertEqual(len(got), 1)
        s, e = got[0]["start"], got[0]["end"]
        self.assertTrue(MIN_LEN <= e - s <= MAX_LEN, (s, e))
        self.assertTrue(any(abs(w["s"] - 0.15 - s) < 0.01 for w in self.tr["words"]), "start isn't on a word")

    def test_too_long_is_cut_under_a_minute(self):
        got = clean_moments([{"start": 100, "end": 200}], self.tr, 1)
        self.assertLessEqual(got[0]["end"] - got[0]["start"], MAX_LEN)

    def test_drops_overlaps_short_ones_and_bad_times(self):
        raw = [{"start": 10, "end": 40}, {"start": 30, "end": 60}, {"start": 100, "end": 105},
               {"start": "x", "end": 9}, {"end": 20}, {"start": 200, "end": 230}]
        got = clean_moments(raw, self.tr, 5)
        self.assertEqual([round(m["start"]) for m in got], [10, 200])
        for a in got:
            for b in got:
                if a is not b:
                    self.assertTrue(a["end"] <= b["start"] or b["end"] <= a["start"])

    def test_stops_at_n(self):
        raw = [{"start": t, "end": t + 30} for t in (0, 100, 200, 300)]
        self.assertEqual(len(clean_moments(raw, self.tr, 2)), 2)

    def test_silence_only_fails_in_plain_words(self):
        tr = {"words": words_every(0.5, 20), "duration": 600}
        with self.assertRaises(RuntimeError) as e:
            clean_moments([{"start": 300, "end": 340}], tr, 1)
        self.assertIn("Couldn't find usable moments", str(e.exception))

    def test_hashtags_and_title_are_tidied(self):
        got = clean_moments([{"start": 10, "end": 40, "title": "T" * 200, "hashtags": ["#vlog", "road trip", "a", "b",
                                                                                         "c", "d"]}], self.tr, 1)
        self.assertEqual(len(got[0]["title"]), 90)
        self.assertEqual(got[0]["hashtags"], ["vlog", "roadtrip", "a", "b", "c"])


class Captions(unittest.TestCase):
    def ass(self, words, a, b, hook=""):
        d = Path(tempfile.mkdtemp(dir=_env.TMP))
        build_ass(words, a, b, hook, "bold", d / "captions_1.ass")
        return (d / "captions_1.ass").read_text(encoding="utf-8")

    @staticmethod
    def secs(t):
        h, m, s = t.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)

    def test_timing_never_goes_backwards(self):
        words = [{"w": "hi", "s": 10.0, "e": 10.0}, {"w": "there", "s": 10.0, "e": 10.3},  # zero-length words
                 *words_every(0.31, 40, start=10.4)]
        lines = [ln for ln in self.ass(words, 10, 40).splitlines() if ln.startswith("Dialogue: 0,")]
        self.assertTrue(lines)
        last = 0
        for ln in lines:
            a, b = ln.split(",")[1:3]
            self.assertGreater(self.secs(b), self.secs(a), ln)
            self.assertGreaterEqual(self.secs(a), last - 0.01, ln)
            last = self.secs(a)

    def test_only_words_inside_the_clip(self):
        words = words_every(1, 100)
        text = self.ass(words, 20, 30)
        self.assertIn("W20", text)
        self.assertNotIn("W50", text)

    def test_hook_banner_and_escaping(self):
        text = self.ass([{"w": "{bad}\\", "s": 0.5, "e": 0.9}], 0, 5, hook="Wait for it 🔥")
        self.assertIn("Hook,,0,0,0,,Wait for it", text)
        self.assertNotIn("🔥", text)
        self.assertNotIn("{BAD}", text)
        self.assertIn("(BAD)", text)

    def test_without_emoji_keeps_words(self):
        self.assertEqual(without_emoji("Road trip 🚗 day 2").replace("  ", " ").strip(), "Road trip day 2")


class Crop(unittest.TestCase):
    def test_landscape_crops_around_the_face(self):
        f = crop_filter({"width": 1920, "height": 1080}, 1500)
        cw, h, x = map(int, re.match(r"crop=(\d+):(\d+):(\d+):0", f).groups())
        self.assertEqual(h, 1080)
        self.assertEqual(cw % 2, 0)
        self.assertEqual(x % 2, 0)
        self.assertLessEqual(x + cw, 1920)
        self.assertTrue(x <= 1500 <= x + cw)

    def test_face_at_the_edge_stays_in_frame(self):
        for cx in (-500, 0, 1919, 5000, None):
            cw, _, x = map(int, re.match(r"crop=(\d+):(\d+):(\d+):0", crop_filter({"width": 1920, "height": 1080},
                                                                                  cx)).groups())
            self.assertTrue(0 <= x and x + cw <= 1920, cx)

    def test_vertical_is_padded_not_cropped(self):
        self.assertTrue(crop_filter({"width": 1080, "height": 1920}, None).startswith("scale="))


class Hooks(unittest.TestCase):
    def test_hook_with_an_unsaid_number_is_dropped(self):
        got = hook_fields({"hooks": {"curiosity": "I lost $2,000 here", "bold": "Never again"}, "hook_pick": "curiosity"},
                          said="we lost the car keys")
        self.assertNotIn("curiosity", got["hooks"])
        self.assertEqual(got["hook"], "Never again")

    def test_said_number_is_kept(self):
        got = hook_fields({"hook": "Day 3 went wrong"}, said="this is day 3 of the trip")
        self.assertEqual(got["hook"], "Day 3 went wrong")
        self.assertEqual(got["hook_mode"], "text")

    def test_nothing_honest_means_no_banner(self):
        got = hook_fields({"hook": "5 secrets"}, said="no numbers here")
        self.assertEqual(got["hook_mode"], "none")


class Transcript(unittest.TestCase):
    def test_repeats_cut_to_two(self):
        words = [{"w": w, "s": 0, "e": 0} for w in "it's snowing everywhere".split()] * 40
        words += [{"w": "ok", "s": 0, "e": 0}]
        out = [w["w"] for w in drop_repeats(words)]
        self.assertEqual(out, "it's snowing everywhere it's snowing everywhere ok".split())

    def test_normal_speech_untouched(self):
        words = [{"w": w, "s": 0, "e": 0} for w in "no no I really mean it".split()]
        self.assertEqual(len(drop_repeats(words)), len(words))


if __name__ == "__main__":
    unittest.main()
