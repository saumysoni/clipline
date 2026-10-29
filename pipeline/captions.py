"""
Burned-in captions: word-by-word highlighted subtitles plus the hook banner, as an .ass file for FFmpeg.

How they look is the Short's own `captions` settings (the editor's Captions tool, web/captions.py), cleaned by
clean_captions(). A Short without them (every Short until a creator changes its captions) uses the preset of the job's
style ("bold", "clean" or "boxed"), which writes exactly what this file always wrote (tests/captions_golden.json).

Settings: on, preset, font (FONTS), size, color / hi / line (#RRGGBB: text, highlighted word, outline or box), outline,
shadow, box (an opaque box behind the line instead of an outline), upper, highlight ("color", "grow" (the spoken word
also grows), "none"), anim ("none", "pop", "punch", "fade", "slide", "words": how each line comes in), bottom (pixels from the bottom of the frame to
the bottom of the captions), words (per line), shift (seconds, + = later), and per word (keyed by its position in
transcript.json's words, so a cut or a trim never moves them to another word): edits (new text, "" = not shown),
pop (emphasis: bigger, in the highlight colour), br (a new line starts at this word) and styles (a look of its own,
LINE_KEYS: the creator styles a few lines differently from the rest; a line takes its first word's).
"""
import re
import shutil
from pathlib import Path

from pipeline.constants import OUT_H, OUT_W
from pipeline.fonts import caption_font_name, font_names
from pipeline.text import without_emoji

_HERE = Path(__file__).parent


def ass_time(t):
    t = max(0.0, t)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def ass_escape(text):
    return without_emoji(text).replace("\\", "").replace("{", "(").replace("}", ")")


# Fonts a creator can choose (bundled, OFL: each folder has the licences). "default" is the caption font of the server
# (CAPTION_FONT, Montserrat ExtraBold in fonts/, else the system bold font: pipeline/fonts.py). The display fonts have one
# weight: asking libass for bold would thicken them artificially, so they're asked for as they are (BOLD).
FONTS = {
    "default": ("Pit Crew bold", None),
    "anton": ("Anton", _HERE / "thumbnails" / "fonts" / "Anton-Regular.ttf"),
    "bebas": ("Bebas Neue", _HERE / "caption_fonts" / "BebasNeue-Regular.ttf"),
    "poppins": ("Poppins Black", _HERE / "caption_fonts" / "Poppins-Black.ttf"),
    "bangers": ("Bangers", _HERE / "caption_fonts" / "Bangers-Regular.ttf"),
    "serif": ("DM Serif Display", _HERE / "thumbnails" / "fonts" / "DMSerifDisplay-Regular.ttf"),
}

BOLD = {"default", "poppins"}
_BASE = {"on": True, "font": "default", "color": "#FFFFFF", "hi": "#FFD60A", "line": "#000000", "box": False,
         "upper": False, "highlight": "color", "anim": "none", "bottom": 560, "words": 3, "shift": 0.0}
# The first three are the job styles chosen when making Shorts (CAPTION_STYLES before October 2026).
PRESETS = {
    "bold": ("Bold", {"size": 92, "outline": 7, "shadow": 2, "upper": True}),
    "clean": ("Clean", {"size": 70, "outline": 2, "shadow": 4}),
    "boxed": ("Boxed", {"size": 74, "outline": 14, "shadow": 0, "box": True}),
    "pop": ("Pop", {"font": "bangers", "size": 104, "outline": 8, "shadow": 3, "upper": True, "hi": "#3DDC84",
                    "highlight": "grow", "anim": "pop", "words": 2}),
    "cinema": ("Cinema", {"font": "bebas", "size": 112, "outline": 5, "shadow": 2, "upper": True, "hi": "#FF5C5C",
                          "anim": "fade"}),
    "minimal": ("Minimal", {"font": "poppins", "size": 68, "outline": 0, "shadow": 4, "highlight": "none", "words": 4}),
    "serif": ("Story", {"font": "serif", "size": 84, "outline": 3, "shadow": 3, "hi": "#FFB4A2", "anim": "fade"}),
}
LIMITS = {"size": (40, 160), "outline": (0, 14), "shadow": (0, 8), "bottom": (400, 1250), "words": (1, 5)}
SHIFT = 0.5  # seconds, either way
CHOICES = {"highlight": ("color", "grow", "none"), "anim": ("none", "pop", "punch", "fade", "slide", "words")}
MAX_EDITS = 2000
POP_STEP = 70  # ms between one word popping in and the next
LINE_KEYS = ("font", "size", "color", "hi", "line", "upper", "bottom")  # what one line can have of its own
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def preset(name):
    """The full settings of a preset (unknown names: Bold)."""
    return {**_BASE, **PRESETS.get(name, PRESETS["bold"])[1], "preset": name if name in PRESETS else "bold",
            "edits": {}, "pop": [], "br": [], "styles": {}}


def _look(out, k, v):
    """Sets out[k] when v is a good value for that look key; True if k is a look key."""
    if k in ("on", "box", "upper"):
        out[k] = bool(v)
    elif k == "font":
        if v in FONTS:
            out[k] = v
    elif k in ("color", "hi", "line"):
        if isinstance(v, str) and HEX.match(v):
            out[k] = v.upper()
    elif k in LIMITS:
        try:
            lo, hi = LIMITS[k]
            out[k] = int(min(hi, max(lo, round(float(v)))))
        except (TypeError, ValueError):
            pass
    elif k in CHOICES:
        if v in CHOICES[k]:
            out[k] = v
    else:
        return False
    return True


def clean_captions(raw, style="bold"):
    """Settings to keep: every key checked, anything missing or wrong from the preset (raw's own, else the job style)."""
    raw = raw if isinstance(raw, dict) else {}
    out = preset(raw.get("preset") if raw.get("preset") in PRESETS else style)
    for k, v in raw.items():
        if _look(out, k, v):
            pass
        elif k == "styles" and isinstance(v, dict):
            styles = {}
            for i, look in list(v.items())[:MAX_EDITS]:
                one = {}
                if str(i).isdigit() and isinstance(look, dict):
                    for lk, lv in look.items():
                        if lk in LINE_KEYS:
                            _look(one, lk, lv)
                if one:
                    styles[str(int(i))] = one
            out[k] = styles
        elif k == "shift":
            try:
                out[k] = round(min(SHIFT, max(-SHIFT, float(v))), 2)
            except (TypeError, ValueError):
                pass
        elif k == "edits" and isinstance(v, dict):
            out[k] = {str(int(i)): " ".join(str(t).split())[:40] for i, t in list(v.items())[:MAX_EDITS]
                      if str(i).isdigit()}
        elif k in ("pop", "br") and isinstance(v, list):
            out[k] = sorted({int(i) for i in v[:MAX_EDITS] if str(i).isdigit()})
    return out


def style_only(caps):
    """The look without the per-word changes (Try again: a new moment has other words)."""
    return {**caps, "edits": {}, "pop": [], "br": [], "styles": {}} if caps else caps


def ass_color(hex_color, alpha=0):
    """#RRGGBB as an ASS colour: &HAABBGGRR (blue, green, red)."""
    r, g, b = hex_color[1:3], hex_color[3:5], hex_color[5:7]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def caption_font(key, job_fonts):
    """The name libass should ask for: a chosen font is copied into the job's fonts folder (gotchas 4 and 25)."""
    path = FONTS.get(key, FONTS["default"])[1]
    if path and path.exists():
        job_fonts = Path(job_fonts)
        job_fonts.mkdir(exist_ok=True)
        if not (job_fonts / path.name).exists():
            shutil.copy(path, job_fonts / path.name)
        names = font_names(path)
        if names:
            return names[1]
    return caption_font_name(job_fonts)


def lines_of(words, caps):
    """The caption lines: the words shown (edited text; "" = left out), `words` to a line, a new line at each br."""
    edits, br, n = caps["edits"], set(caps["br"]), caps["words"]
    shown = []
    for w in words:
        i = w.get("i")
        text = edits.get(str(i), w["w"]) if i is not None else w["w"]
        if text.strip():
            shown.append({**w, "w": text})
    lines = []
    for w in shown:
        if not lines or len(lines[-1]) >= n or (w.get("i") is not None and w["i"] in br):
            lines.append([])
        lines[-1].append(w)
    return lines


def build_ass(words, clip_start, clip_end, hook, style, path, caps=None):
    """words: the Short's words on its own clock ({"w", "s", "e"}, and "i" = its position in transcript.json)."""
    c = clean_captions(caps, style) if caps else preset(style if style in PRESETS else "bold")
    font = caption_font_name(Path(path).parent / "fonts")
    cfont = caption_font(c["font"], Path(path).parent / "fonts")
    text, hi = ass_color(c["color"]), ass_color(c["hi"])
    line = ass_color(c["line"], 0x40 if c["box"] else 0)
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {OUT_W}
PlayResY: {OUT_H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{cfont},{c["size"]},{text},{text},{line},&H80000000,{-1 if c["font"] in BOLD else 0},0,0,0,100,100,0,0,{3 if c["box"] else 1},{c["outline"]},{c["shadow"]},2,80,80,{c["bottom"]},1
Style: Hook,{font},66,&H00111111,&H00111111,&H00FFFFFF,&H00FFFFFF,-1,0,0,0,100,100,0,0,3,18,0,8,90,90,200,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    out = []
    if c["on"]:
        sh = c["shift"]
        clip = [{**w, "s": w["s"] + sh, "e": w["e"] + sh} for w in words
                if w["s"] >= clip_start - 0.05 and w["e"] <= clip_end + 0.05]
        pop, mode = set(c["pop"]), c["highlight"]
        chunks = lines_of(clip, c)
        for ci, chunk in enumerate(chunks):
            nxt = chunks[ci + 1][0]["s"] if ci + 1 < len(chunks) else None
            # a line with a look of its own (its first word's): override tags at its start, its own height
            own = c["styles"].get(str(chunk[0].get("i")), {})
            lc = {**c, **own}
            ltext, lhi = ass_color(lc["color"]), ass_color(lc["hi"])
            tags = ""
            if own:
                if lc["font"] != c["font"]:
                    tags += f"\\fn{caption_font(lc['font'], Path(path).parent / 'fonts')}\\b{1 if lc['font'] in BOLD else 0}"
                if lc["size"] != c["size"]:
                    tags += f"\\fs{lc['size']}"
                if lc["color"] != c["color"]:
                    tags += f"\\c{ltext}&"
                if lc["line"] != c["line"]:
                    tags += f"\\3c{ass_color(lc['line'])}&"
            margin = lc["bottom"] if own and lc["bottom"] != c["bottom"] else 0
            for wi, w in enumerate(chunk):
                start = w["s"] - clip_start
                if wi + 1 < len(chunk):
                    end = chunk[wi + 1]["s"] - clip_start
                else:
                    end = w["e"] - clip_start
                    if nxt is not None and nxt - w["e"] < 0.6:
                        end = nxt - clip_start
                if end <= start:
                    end = start + 0.08
                if end <= 0:
                    continue
                # How a line comes in (its first event; "words" on every event):
                #   pop    its words pop in one after another (POP_STEP apart), each growing from small past its own
                #          size, a little under, then settling: a bounce
                #   punch  every word slams in at 150 %, blurred, and snaps to its size in 0.1 s
                #   fade   the whole line fades in slowly (0.45 s), no movement
                #   slide  the line rises 70 px into place as it fades in (0.16 s)
                #   words  each word shows when it's said; the ones still to come keep their room, so nothing shifts
                # Scale effects go on every word, each to its own size: a word's own scale tag stops a line-wide one.
                anim = c["anim"] if wi == 0 or c["anim"] == "words" else "none"
                alphas = (0, 0x40 if lc["box"] else 0, 0x80)  # text, outline or box, shadow: as the style has them
                hide = "".join(f"\\{n}a&HFF&" for n in (1, 3, 4))
                parts = []
                for j, x in enumerate(chunk):
                    t = ass_escape(x["w"].upper() if lc["upper"] else x["w"])
                    big = x.get("i") is not None and x["i"] in pop
                    now = j == wi and mode != "none"
                    scale = (125 if big and now and mode == "grow" else 118) if big or (now and mode == "grow") else 100
                    tag = f"\\c{lhi}&" if big or now else ""
                    moved = anim in ("pop", "punch")
                    if anim == "pop":
                        d, lo, up, under = j * POP_STEP, scale * 2 // 5, scale * 5 // 4, scale * 19 // 20
                        show = "".join(f"\\{n}a&H{a:02X}&" for n, a in zip((1, 3, 4), alphas)) if j else ""
                        tag += ((hide if j else "") + f"\\fscx{lo}\\fscy{lo}"
                                + (f"\\t({d},{d + 1},{show})" if j else "")
                                + f"\\t({d},{d + 120},\\fscx{up}\\fscy{up})\\t({d + 120},{d + 200},\\fscx{under}\\fscy{under})"
                                f"\\t({d + 200},{d + 270},\\fscx{scale}\\fscy{scale})")
                    elif anim == "punch":
                        tag += f"\\fscx{scale * 3 // 2}\\fscy{scale * 3 // 2}\\blur4\\t(0,100,\\fscx{scale}\\fscy{scale}\\blur0)"
                    elif scale != 100:
                        tag += f"\\fscx{scale}\\fscy{scale}"
                    if anim == "words" and j == wi + 1:
                        tag += hide  # this word and the rest of the line: not said yet
                    back = (f"\\c{ltext}&" if big or now else "") + ("\\fscx100\\fscy100" if scale != 100 or moved else "")
                    parts.append((f"{{{tag}}}" if tag else "") + t + (f"{{{back}}}" if back else ""))
                intro = "{" + tags + "}" if tags else ""
                if anim == "fade":
                    intro += "{\\fad(450,0)}"
                elif anim == "slide":
                    y = OUT_H - (margin or c["bottom"])
                    intro += f"{{\\move({OUT_W // 2},{y + 70},{OUT_W // 2},{y},0,160)\\fad(120,0)}}"
                out.append(f"Dialogue: 0,{ass_time(max(0.0, start))},{ass_time(end)},Cap,,0,0,{margin},,{intro}{' '.join(parts)}")
    if hook:
        out.append(f"Dialogue: 1,{ass_time(0)},{ass_time(2.8)},Hook,,0,0,0,,{ass_escape(hook)}")
    Path(path).write_text(head + "\n".join(out) + "\n", encoding="utf-8")
