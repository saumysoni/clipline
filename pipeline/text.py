"""
Small text helpers: times as m:ss, reading typed times, removing emoji, what was said between two times.
"""
import re


def fmt_mmss(sec):
    sec = int(sec)
    return f"{sec // 60}:{sec % 60:02d}"


def parse_time(text):
    """Seconds from what a creator types: 2:10, 1:02:10, 130 or 130.5. None if it isn't a time."""
    text = str(text or "").strip()
    if not re.fullmatch(r"\d+(:\d{1,2}){0,2}(\.\d+)?", text):
        return None
    sec = 0.0
    for part in text.split(":"):
        sec = sec * 60 + float(part)
    return sec


def said_between(transcript, start, end):
    return " ".join(w["w"] for w in transcript["words"] if start <= w["s"] < end)


def without_emoji(text):
    """Text without emoji and other pictographs: the caption and thumbnail fonts have none, so they'd
    show as empty boxes. (They're fine in titles and descriptions, which YouTube displays itself.)"""
    import unicodedata
    out = "".join(c for c in (text or "") if not (
        ord(c) >= 0x1F000 or unicodedata.category(c) in ("So", "Cs") or ord(c) in (0xFE0F, 0x200D, 0x20E3)))
    return re.sub(r"\s+([?!.,])", r"\1", " ".join(out.split()))
