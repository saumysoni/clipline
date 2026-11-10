"""
Text on screen (the editor's Text & Overlays tool, web/overlays.py): a few lines of text a creator puts on a Short at a
moment they choose, burned in by libass with the captions (pipeline/captions.py build_ass: same .ass file, same fonts).

A Short's `overlays` is a list (at most MAX) of
  {id, text (up to 3 lines), style (STYLES), font (captions.FONTS), color / line (#RRGGBB: the text, and its outline,
   box or shadow), size (SIZES), x, y (where its middle is, fractions of the 1080x1920 picture), a, b (when it shows, in
   the vlog's seconds), anim (ANIMS: how it comes in)}.
Times are the vlog's seconds, like pieces, caption edits and reframe moves, so a cut or a trim never moves text off the
moment it was put on: it shows in each kept part of a..b (one event per part), and not at all if all of it was cut.
"""
import re

from pipeline.captions import BOLD, FONTS, HEX, ass_color, ass_escape, ass_time, caption_font
from pipeline.constants import OUT_H, OUT_W

MAX = 6            # overlays on one Short: more than this crowds a 9:16 picture
MAX_TEXT = 120     # characters
MAX_LINES = 3
MIN_LEN = 0.3      # seconds on screen, at least
MAX_LEN = 60.0
STYLES = {  # name on the page; outline, shadow; box (BorderStyle 3); hollow (the text itself see-through)
    "bold": ("Bold", 6, 2, False, False),
    "boxed": ("Boxed", 18, 0, True, False),
    "shadow": ("Shadow", 0, 5, False, False),
    "hollow": ("Outline", 5, 0, False, True),
}
SIZES = {"s": 72, "m": 100, "l": 136}  # pixels, at 1080 wide
ANIMS = ("none", "pop", "fade", "slide")
EDGE = 0.04        # how close to the picture's edge the middle of a text can be
_ID = re.compile(r"^[A-Za-z0-9_-]{1,16}$")


def _num(v, lo, hi, default):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    return min(hi, max(lo, v)) if v == v else default


def _text(v):
    """Up to MAX_LINES lines, each with its spaces tidied; "" when there's nothing to show."""
    if not isinstance(v, str):
        return ""
    lines = [" ".join(line.split()) for line in v.replace("\r", "").split("\n")]
    lines = [line for line in lines if line][:MAX_LINES]
    return "\n".join(lines)[:MAX_TEXT].strip()


def clean_overlays(raw, duration=0.0):
    """What to keep: every key checked, anything wrong left at its default; overlays without words or time dropped.
    duration: the vlog's length (0 = unknown, times aren't capped). None when there's nothing."""
    if not isinstance(raw, list):
        return None
    out, seen = [], set()
    for n, o in enumerate(raw):
        if len(out) >= MAX:
            break
        if not isinstance(o, dict):
            continue
        text = _text(o.get("text"))
        if not text:
            continue
        a = round(_num(o.get("a"), 0.0, duration or 1e9, -1.0), 2)
        if a < 0:
            continue
        top = min(a + MAX_LEN, duration) if duration else a + MAX_LEN
        b = round(_num(o.get("b"), a, top, a + 2.5), 2)
        if b - a < MIN_LEN:
            if top - a < MIN_LEN:
                continue
            b = round(a + MIN_LEN, 2)
        oid = str(o.get("id", ""))
        if not _ID.match(oid) or oid in seen:
            oid = f"t{n}"
            while oid in seen:
                oid += "x"
        seen.add(oid)
        color = o.get("color") if isinstance(o.get("color"), str) and HEX.match(o["color"]) else "#FFFFFF"
        line = o.get("line") if isinstance(o.get("line"), str) and HEX.match(o["line"]) else "#000000"
        out.append({
            "id": oid, "text": text,
            "style": o.get("style") if o.get("style") in STYLES else "bold",
            "font": o.get("font") if o.get("font") in FONTS else "default",
            "color": color.upper(), "line": line.upper(),
            "size": o.get("size") if o.get("size") in SIZES else "m",
            "x": round(_num(o.get("x"), EDGE, 1 - EDGE, 0.5), 4), "y": round(_num(o.get("y"), EDGE, 1 - EDGE, 0.3), 4),
            "a": a, "b": b,
            "anim": o.get("anim") if o.get("anim") in ANIMS else "none",
        })
    return out or None


def on_short(pieces, a, b):
    """When a..b (vlog seconds) shows on the Short's own clock: [(start, end), ...], one per kept piece it's in."""
    out, at = [], 0.0
    for pa, pb in pieces:
        s, e = max(a, pa), min(b, pb)
        if e - s >= 0.05:
            out.append((at + s - pa, at + e - pa))
        at += pb - pa
    return out


def overlay_styles(font):
    """The .ass Style lines overlays use (font: the job's caption font; each event names its own)."""
    return (f"Style: Ovl,{font},84,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,2,5,90,90,0,1\n"
            f"Style: OvlBox,{font},84,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,3,18,0,5,90,90,0,1\n")


def overlay_events(overlays, pieces, job_fonts):
    """Dialogue lines (layer 2, over the captions and the hook) for these overlays (clean_overlays()) on the Short the
    pieces make."""
    lines = []
    for o in overlays or []:
        spans = on_short(pieces, o["a"], o["b"])
        if not spans:
            continue
        _, bord, shad, box, hollow = STYLES[o["style"]]
        x, y = round(o["x"] * OUT_W), round(o["y"] * OUT_H)
        text = "\\N".join(ass_escape(part) for part in o["text"].split("\n"))
        fn = caption_font(o["font"], job_fonts)
        look = f"\\fn{fn}\\b{1 if o['font'] in BOLD else 0}\\fs{SIZES[o['size']]}"
        if hollow:  # the text see-through, its outline in the text's colour
            look += f"\\1a&HFF&\\3c{_bgr(o['color'])}\\bord{bord}\\shad0"
        elif o["style"] == "shadow":
            look += f"\\c{_bgr(o['color'])}\\4c{_bgr(o['line'])}\\4a&H50&\\bord0\\shad{shad}\\blur1"
        else:
            look += f"\\c{_bgr(o['color'])}\\3c{_bgr(o['line'])}\\bord{bord}\\shad{shad}"
        for k, (s, e) in enumerate(spans):
            anim = o["anim"] if k == 0 else "none"
            if anim == "slide":
                place = f"\\an5\\move({x},{y + 80},{x},{y},0,220)\\fad(150,0)"
            else:
                place = f"\\an5\\pos({x},{y})"
                if anim == "pop":
                    place += "\\fscx40\\fscy40\\t(0,140,\\fscx112\\fscy112)\\t(140,230,\\fscx100\\fscy100)"
                elif anim == "fade":
                    place += "\\fad(300,250)"
            lines.append(f"Dialogue: 2,{ass_time(s)},{ass_time(e)},{'OvlBox' if box else 'Ovl'},,0,0,0,,"
                         f"{{{place}{look}}}{text}")
    return lines


def _bgr(hex_color):
    """#RRGGBB as an ASS colour tag value: &HBBGGRR&."""
    return ass_color(hex_color)[:2] + ass_color(hex_color)[4:] + "&"
