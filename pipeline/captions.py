"""
Burned-in captions: word-by-word highlighted subtitles plus the hook banner, as an .ass file for FFmpeg.
"""
from pathlib import Path

from pipeline.constants import OUT_H, OUT_W
from pipeline.fonts import caption_font_name
from pipeline.text import without_emoji


def ass_time(t):
    t = max(0.0, t)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def ass_escape(text):
    return without_emoji(text).replace("\\", "").replace("{", "(").replace("}", ")")


CAPTION_STYLES = {
    # name: (fontsize, borderstyle, outline, shadow, outline colour, uppercase)
    "bold":  (92, 1, 7, 2, "&H00000000", True),
    "clean": (70, 1, 2, 4, "&H00000000", False),
    "boxed": (74, 3, 14, 0, "&H40000000", False),
}


YELLOW = "&H000AD6FF&"  # #FFD60A in ASS (BGR) order


def build_ass(words, clip_start, clip_end, hook, style, path):
    fs, bs, ol, sh, oc, upper = CAPTION_STYLES.get(style, CAPTION_STYLES["bold"])
    font = caption_font_name(Path(path).parent / "fonts")
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {OUT_W}
PlayResY: {OUT_H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},{fs},&H00FFFFFF,&H00FFFFFF,{oc},&H80000000,-1,0,0,0,100,100,0,0,{bs},{ol},{sh},2,80,80,560,1
Style: Hook,{font},66,&H00111111,&H00111111,&H00FFFFFF,&H00FFFFFF,-1,0,0,0,100,100,0,0,3,18,0,8,90,90,200,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    clip = [w for w in words if w["s"] >= clip_start - 0.05 and w["e"] <= clip_end + 0.05]
    chunks = [clip[i:i + 3] for i in range(0, len(clip), 3)]
    for ci, chunk in enumerate(chunks):
        nxt = chunks[ci + 1][0]["s"] if ci + 1 < len(chunks) else None
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
            parts = []
            for j, x in enumerate(chunk):
                t = ass_escape(x["w"].upper() if upper else x["w"])
                parts.append(f"{{\\c{YELLOW}}}{t}{{\\c&H00FFFFFF&}}" if j == wi else t)
            lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Cap,,0,0,0,,{' '.join(parts)}")
    if hook:
        lines.append(f"Dialogue: 1,{ass_time(0)},{ass_time(2.8)},Hook,,0,0,0,,{ass_escape(hook)}")
    Path(path).write_text(head + "\n".join(lines) + "\n", encoding="utf-8")
