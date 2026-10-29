"""Captions (pipeline/captions.py, web/captions.py): a Short's own caption settings, cleaned; the .ass they make (the
default exactly as before, tests/captions_golden.json); word changes keyed by the word's place in the transcript;
saving with and without a remake; other remakes (hook, cut, Try again) keeping them; the preview's errors."""
from tests import fakes as F

import json
import tempfile
import unittest
from pathlib import Path

from pipeline import captions as C
from settings import JOBS_DIR

GOLDEN = json.loads((Path(__file__).parent / "captions_golden.json").read_text(encoding="utf-8"))


def ass(words, caps=None, style="bold", hook=""):
    d = Path(tempfile.mkdtemp())
    C.build_ass(words, 0.0, 30.0, hook, style, d / "c.ass", caps)
    return (d / "c.ass").read_text(encoding="utf-8"), d


def W(*texts, gap=0.4):
    return [{"w": t, "s": round(k * gap, 3), "e": round(k * gap + 0.3, 3), "i": 100 + k} for k, t in enumerate(texts)]


def dialogue(text):
    return [ln.split(",Cap,,0,0,0,,", 1)[1] for ln in text.splitlines() if ln.startswith("Dialogue: 0,")]


def style_line(text):
    return next(ln for ln in text.splitlines() if ln.startswith("Style: Cap,")).split(",")


class Build(unittest.TestCase):
    def test_default_is_exactly_as_before(self):
        """No settings, settings cleaned from nothing, and each preset as-is: the same file the old code wrote."""
        for key, want in GOLDEN["out"].items():
            style, hook = key.split("|")
            for caps in (None, C.clean_captions({}, style), C.preset(style)):
                d = Path(tempfile.mkdtemp())
                C.build_ass(GOLDEN["words"], 0.0, 8.0, hook, style, d / "c.ass", caps)
                self.assertEqual((d / "c.ass").read_text(encoding="utf-8"), want, key)

    def test_colours_are_blue_green_red(self):
        self.assertEqual(C.ass_color("#FFD60A"), "&H000AD6FF")
        self.assertEqual(C.ass_color("#112233", 0x40), "&H40332211")

    def test_clean(self):
        c = C.clean_captions({"preset": "pop", "size": 999, "bottom": 5, "words": 0, "shift": 9, "color": "red",
                              "hi": "#00ff00", "font": "comic-sans", "highlight": "wobble", "anim": "fade",
                              "edits": {"12": "  hello   there ", "x": "no", "13": "a" * 90}, "pop": [3, "4", "z", 3],
                              "br": "nope", "on": 0, "junk": 1})
        self.assertEqual((c["size"], c["bottom"], c["words"], c["shift"]), (160, 400, 1, 0.5))
        self.assertEqual((c["color"], c["hi"], c["font"], c["highlight"], c["anim"]), ("#FFFFFF", "#00FF00", "bangers", "grow", "fade"))
        self.assertEqual(c["edits"], {"12": "hello there", "13": "a" * 40})
        self.assertEqual((c["pop"], c["br"], c["on"]), ([3, 4], [], False))
        self.assertNotIn("junk", c)
        self.assertEqual(C.clean_captions(None, "clean")["size"], 70)  # nothing saved: the job's style
        self.assertEqual(C.clean_captions("garbage", "nope")["preset"], "bold")
        self.assertEqual(C.style_only({**c, "pop": [1]})["pop"], [])

    def test_look(self):
        caps = {**C.preset("bold"), "color": "#112233", "hi": "#00FF00", "line": "#445566", "size": 120, "bottom": 900,
                "outline": 3, "upper": False}
        text, _ = ass(W("one", "two", "three"), caps)
        st = style_line(text)
        self.assertEqual((st[2], st[3], st[5], st[16], st[-2]), ("120", "&H00332211", "&H00665544", "3", "900"))
        self.assertIn("{\\c&H0000FF00&}one{\\c&H00332211&} two three", dialogue(text)[0])
        boxed, _ = ass(W("one"), {**caps, "box": True})
        self.assertEqual((style_line(boxed)[5], style_line(boxed)[15]), ("&H40665544", "3"))  # a see-through box
        none, _ = ass(W("one", "two"), {**caps, "highlight": "none"})
        self.assertEqual(dialogue(none)[0], "one two")
        grow, _ = ass(W("one", "two"), {**caps, "highlight": "grow"})
        self.assertIn("\\fscx118", dialogue(grow)[0])
        self.assertEqual(dialogue(ass(W("one"), {**caps, "on": False})[0]), [])  # captions off
        hooked, _ = ass(W("one"), {**caps, "on": False}, hook="The hook")
        self.assertIn("Hook,,0,0,0,,The hook", hooked)  # no captions, the hook stays

    def test_fonts_are_bundled_and_copied_into_the_job(self):
        for key, (name, path) in C.FONTS.items():
            if key == "default":
                continue
            self.assertTrue(path.exists(), path)
            text, d = ass(W("one"), {**C.preset("bold"), "font": key})
            self.assertEqual(style_line(text)[1], C.font_names(path)[1], key)  # the full name (gotcha 25)
            self.assertTrue((d / "fonts" / path.name).exists())
            self.assertTrue(list(path.parent.glob("OFL*.txt")), "licence next to " + path.name)
        self.assertEqual(style_line(ass(W("one"), {**C.preset("pop")})[0])[1], "Bangers")

    def test_a_chosen_font_never_becomes_the_default(self):
        """Choosing Anton copies it into the job's fonts folder; the other Shorts and the hook keep the default font,
        whatever sorts first (the system bold font when fonts/ has no Montserrat)."""
        import shutil
        d = Path(tempfile.mkdtemp())
        (d / "fonts").mkdir()
        shutil.copy(C.FONTS["poppins"][1], d / "fonts" / "zz-fallback.ttf")  # stands in for Arial Bold / DejaVu
        default = C.caption_font_name(d / "fonts")
        self.assertEqual(default, "Poppins Black")
        for key in ("anton", "bangers", "bebas", "serif"):
            C.caption_font(key, d / "fonts")
        self.assertEqual(C.caption_font_name(d / "fonts"), default)
        C.build_ass(W("one"), 0.0, 30.0, "A hook", "bold", d / "c.ass")
        text = (d / "c.ass").read_text(encoding="utf-8")
        self.assertEqual((style_line(text)[1], text.split("Style: Hook,")[1].split(",")[0]), (default, default))

    def test_a_few_lines_look_different(self):
        """styles: a look of its own on some words; a line takes its first word's, the rest stay as they are."""
        words = W("so", "we", "made", "it", "to", "the", "top")
        own = {"font": "bangers", "size": 130, "color": "#00FF00", "hi": "#FF00FF", "line": "#FFFFFF", "bottom": 1100,
               "upper": False}
        caps = {**C.preset("bold"), "styles": {"103": own, "104": own, "105": own}}
        text, d = ass(words, caps)
        rows = [ln for ln in text.splitlines() if ln.startswith("Dialogue: 0,")]
        styled = [ln for ln in rows if ",Cap,,0,0,1100,," in ln]
        self.assertEqual(len(styled), 3, rows)  # the line "it to the", one event a word
        self.assertIn("{\\fnBangers\\b0\\fs130\\c&H0000FF00&\\3c&H00FFFFFF&}", styled[0])
        self.assertIn("{\\c&H00FF00FF&}to{\\c&H0000FF00&}", styled[1])  # its own highlight, back to its own text colour
        self.assertIn("}it", styled[0])  # its own capitals setting (the rest are in capitals)
        self.assertNotIn("IT", styled[0])
        self.assertTrue((d / "fonts" / "Bangers-Regular.ttf").exists())
        rest = [ln for ln in rows if ln not in styled]
        self.assertEqual(len(rest), 4)
        self.assertTrue(all(",Cap,,0,0,0,," in ln and "\\fn" not in ln and "\\fs" not in ln for ln in rest), rest)
        # a line takes its first word's look: three words a line from "we" -> "we made it" is plain, "to the top" styled
        text, _ = ass(words, {**caps, "styles": {"104": own}})
        self.assertEqual([ln.split(",,", 2)[1] for ln in text.splitlines() if ln.startswith("Dialogue: 0,")].count("0,0,1100"), 0)
        c = C.clean_captions({"styles": {"5": {"size": 999, "font": "nope", "color": "red", "words": 4, "on": False},
                                         "6": {"junk": 1}, "x": {"size": 80}}})
        self.assertEqual(c["styles"], {"5": {"size": 160}})  # only a line's keys, checked; nothing left = dropped
        self.assertEqual(C.style_only(c)["styles"], {})

    def test_words_lines_and_timing(self):
        words = W("so", "we", "made", "it", "to", "the", "top")
        caps = {**C.preset("bold"), "upper": False, "words": 2, "edits": {"102": "MADE!", "104": ""}, "br": [106],
                "pop": [101]}
        lines = [" ".join(w["w"] for w in ln) for ln in C.lines_of(words, C.clean_captions(caps))]
        self.assertEqual(lines, ["so we", "MADE! it", "the", "top"])  # "to" left out, a new line at "top"
        text, _ = ass(words, caps)
        self.assertIn("\\fscx118\\fscy118}we", dialogue(text)[0])  # emphasis: bigger, in the highlight colour
        later, _ = ass(words, {**caps, "shift": 0.3})
        self.assertTrue(later.splitlines()[-1].startswith("Dialogue: 0,0:00:02.70"))  # "top" at 2.4 s, 0.3 s later
        early, _ = ass(words, {**caps, "shift": -0.5})
        self.assertTrue(all(",0:00:00.00," not in ln.split(",Cap,")[0][14:] for ln in early.splitlines()
                            if ln.startswith("Dialogue")))  # nothing ends at 0 (dropped instead)
        for anim, tag in (("pop", "\\t(0,120"), ("punch", "\\blur4"), ("fade", "\\fad(450,0)"), ("slide", "\\move(")):
            t, _ = ass(words, {**caps, "anim": anim})
            starts = [ln for ln in dialogue(t) if tag in ln]
            self.assertEqual(len(starts), 4, anim)  # once per line (as it comes in), not per word
        # pop: the words pop in one after another, each to its own size (the spoken word with "grow" is bigger)
        t, _ = ass(W("one", "two", "three"), {**C.preset("bold"), "anim": "pop", "highlight": "grow"})
        first = dialogue(t)[0]
        self.assertIn("\\fscx47\\fscy47\\t(0,120,\\fscx147\\fscy147)", first)  # ONE: the spoken word, 118 %
        self.assertIn("\\1a&HFF&\\3a&HFF&\\4a&HFF&\\fscx40\\fscy40\\t(70,71,\\1a&H00&\\3a&H00&\\4a&H80&)", first)  # TWO later
        self.assertIn("\\t(140,141,", first)  # THREE later still
        self.assertNotIn("\\t(", dialogue(t)[1])  # the next word's event: the line is already in
        # punch: every word slams in and snaps to its own size
        t, _ = ass(W("one", "two"), {**C.preset("bold"), "anim": "punch", "highlight": "grow"})
        self.assertIn("\\fscx177\\fscy177\\blur4\\t(0,100,\\fscx118\\fscy118\\blur0)}ONE", dialogue(t)[0])
        self.assertIn("\\fscx150\\fscy150\\blur4\\t(0,100,\\fscx100\\fscy100\\blur0)}TWO", dialogue(t)[0])
        # slide: up into its own place (the line's own height when it has one)
        t, _ = ass(W("one"), {**C.preset("bold"), "anim": "slide", "bottom": 900})
        self.assertIn("\\move(540,1090,540,1020,0,160)", dialogue(t)[0])
        # word by word: the words still to come are there (no shifting) but not shown
        t, _ = ass(W("one", "two", "three"), {**C.preset("bold"), "anim": "words"})
        d = dialogue(t)
        self.assertTrue(d[0].startswith("{\\c&H000AD6FF&}ONE{\\c&H00FFFFFF&} {\\1a&HFF&\\3a&HFF&\\4a&HFF&}TWO THREE"), d[0])
        self.assertIn("{\\c&H000AD6FF&}TWO{\\c&H00FFFFFF&} {\\1a&HFF&", d[1])
        self.assertNotIn("a&HFF&", d[2])  # the last word: the whole line
        self.assertEqual(C.clean_captions({"anim": "words"})["anim"], "words")


class Routes(unittest.TestCase):
    def setUp(self):
        F.install()
        F.reset()
        self.u = F.new_user()
        self.c = F.client(self.u)
        self.jid, st = F.make_shorts(self.c, 150, 2)
        self.s = st["shorts"][0]
        self.base = f"/api/captions/{self.jid}/{self.s['idx']}"

    def short(self):
        return F.wait(lambda: (x := next(y for y in F.job_json(self.jid)["shorts"] if y["idx"] == self.s["idx"]))
                      and not x.get("retrying") and x, what="remade")

    def ass_of(self, me):
        return (JOBS_DIR / self.jid / me["video"].replace("short_", "captions_").replace(".mp4", ".ass")).read_text()

    def test_info(self):
        j = self.c.get(self.base).json
        self.assertTrue(j["can_apply"])
        self.assertEqual(j["captions"], C.preset("bold"))
        self.assertEqual([p["id"] for p in j["presets"]][:3], ["bold", "clean", "boxed"])
        self.assertIn("bangers", [f["id"] for f in j["fonts"]])
        self.assertEqual(self.c.get(f"/api/captions/{self.jid}/99").status_code, 404)
        self.assertEqual(F.client(F.new_user()).get(self.base).status_code, 404)  # only its owner
        # AI Edit's words carry their place in the transcript (what word changes key on)
        words = self.c.get(f"/api/ai-edit/{self.jid}/{self.s['idx']}").json["words"]
        tr = json.loads((JOBS_DIR / self.jid / "transcript.json").read_text())
        self.assertTrue(all(tr["words"][w["i"]]["s"] == w["s"] for w in words))

    def test_save_and_remake(self):
        words = self.c.get(f"/api/ai-edit/{self.jid}/{self.s['idx']}").json["words"]
        i = words[1]["i"]
        caps = {**C.preset("cinema"), "edits": {str(i): "Nagaland"}, "bottom": 1000}
        r = self.c.post(self.base, json={"captions": caps, "remake": True})
        self.assertEqual(r.status_code, 200, r.json)
        me = self.short()
        self.assertFalse(me.get("retry_error"), me.get("retry_error"))
        self.assertNotEqual(me["video"], self.s["video"])
        self.assertEqual(me["captions"]["preset"], "cinema")
        text = self.ass_of(me)
        self.assertIn("NAGALAND", text)  # cinema is upper case
        self.assertEqual(style_line(text)[1], "Bebas Neue")
        self.assertEqual(style_line(text)[-2], "1000")
        self.assertEqual(self.c.get(self.base).json["captions"]["edits"], {str(i): "Nagaland"})

    def test_save_without_remake_then_a_hook_and_a_cut_keep_them(self):
        """The editor saves captions without a remake when a cut or a hook remakes the Short anyway."""
        video = self.s["video"]
        self.assertEqual(self.c.post(self.base, json={"captions": C.preset("pop"), "remake": False}).status_code, 200)
        me = self.short()
        self.assertEqual((me["video"], me["captions"]["preset"]), (video, "pop"))  # saved, not remade
        self.c.post(f"/api/hook/{self.jid}/{self.s['idx']}", json={"mode": "text", "text": "Wait for it"})
        me = self.short()
        self.assertEqual(F.RENDERED[-1]["captions"]["preset"], "pop")
        self.assertEqual(style_line(self.ass_of(me))[1], "Bangers")
        s, e = self.s["start"], self.s["end"]
        self.c.post(f"/api/ai-edit/{self.jid}/{self.s['idx']}/apply", json={"pieces": [[s, s + 6], [s + 9, e]]})
        me = self.short()
        self.assertEqual((me["captions"]["preset"], F.RENDERED[-1]["captions"]["preset"]), ("pop", "pop"))

    def test_try_again_keeps_the_look_not_the_words(self):
        caps = {**C.preset("serif"), "edits": {"5": "x"}, "pop": [5], "br": [6]}
        self.c.post(self.base, json={"captions": caps, "remake": False})
        self.assertEqual(self.c.post(f"/api/retry/{self.jid}/{self.s['idx']}", json={}).status_code, 200)
        me = self.short()
        self.assertFalse(me.get("retry_error"), me.get("retry_error"))
        self.assertEqual(me["captions"]["preset"], "serif")
        self.assertEqual((me["captions"]["edits"], me["captions"]["pop"], me["captions"]["br"]), ({}, [], []))

    def test_refused(self):
        self.assertEqual(self.c.post(self.base, json={"captions": "nope"}).status_code, 400)
        from web.store import update_short
        update_short(self.jid, self.s["idx"], retrying=True)
        self.assertIn("still being made", self.c.post(self.base, json={"captions": {}}).json["error"])
        update_short(self.jid, self.s["idx"], retrying=False)
        for f in (JOBS_DIR / self.jid).glob("source.*"):
            f.unlink()
        r = self.c.post(self.base, json={"captions": {}, "remake": True})
        self.assertIn("video was deleted", r.json["error"])
        self.assertFalse(self.c.get(self.base).json["can_apply"])
        self.assertEqual(self.c.post(self.base + "/preview", json={}).status_code, 400)

    def test_preview_route(self):
        """Drawing is checked with the real FFmpeg in tests/system; here: what it's given, and bad input."""
        import pipeline
        seen = {}

        def frame(src, meta, moment, words, at, style, job_dir, caps=None):
            seen.update(moment=moment, at=at, caps=caps)
            return b"\xff\xd8jpeg"
        real, pipeline.caption_frame = pipeline.caption_frame, frame
        try:
            s = self.s["start"]
            r = self.c.post(self.base + "/preview", json={"captions": C.preset("minimal"), "at": s + 3,
                                                           "pieces": [[s, s + 5], [s + 8, s + 20]]})
            self.assertEqual((r.status_code, r.mimetype, r.data), (200, "image/jpeg", b"\xff\xd8jpeg"))
            self.assertEqual((seen["at"], seen["caps"]["preset"], seen["moment"]["pieces"]),
                             (s + 3, "minimal", [[s, s + 5], [s + 8, s + 20]]))
            self.assertEqual(self.c.post(self.base + "/preview", json={"at": "soon"}).status_code, 400)
        finally:
            pipeline.caption_frame = real


if __name__ == "__main__":
    unittest.main()
