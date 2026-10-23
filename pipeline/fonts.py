"""
Fonts for burned-in captions and thumbnails (the fonts/ folder, or a system bold font).
"""
import os
import shutil
from pathlib import Path

from pipeline.constants import FONTS_DIR


def find_font_file():
    """A bold TTF/OTF for thumbnails. Put your own in ./fonts to control the look."""
    if FONTS_DIR.exists():
        for f in sorted(FONTS_DIR.iterdir()):
            if f.suffix.lower() in (".ttf", ".otf"):
                return str(f)
    for f in [
        "C:/Windows/Fonts/arialbd.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]:
        if os.path.exists(f):
            return f
    return None


def font_family(path):
    try:
        from PIL import ImageFont
        return ImageFont.truetype(str(path), 20).getname()[0]
    except Exception:  # noqa: BLE001
        return None


def font_names(path):
    """(family, full name) of a font file, e.g. ("Montserrat", "Montserrat ExtraBold"), or None."""
    try:
        from PIL import ImageFont
        family, style = ImageFont.truetype(str(path), 20).getname()
    except Exception:  # noqa: BLE001
        return None
    style = (style or "").strip()
    return family, family if style.lower() in ("", "regular") else f"{family} {style}"


def caption_font_name(job_fonts=None):
    """The font name libass should use for burned-in captions.

    Uses CAPTION_FONT when a font in the fonts folder has that family or full name; otherwise the full name of the font
    that is there, so captions never come out in a missing font (or not at all). The full name matters: when the
    system also has the family's other weights (a Linux server with fonts-montserrat), asking for the family
    ("Montserrat") gets Regular, while "Montserrat ExtraBold" gets that exact file (checked on Ubuntu 24.04, Oct 2026).
    """
    wanted = os.getenv("CAPTION_FONT", "Montserrat ExtraBold")
    if not job_fonts or not Path(job_fonts).exists():
        return wanted
    names = [n for n in (font_names(p) for p in sorted(Path(job_fonts).iterdir())
                         if p.suffix.lower() in (".ttf", ".otf")) if n]
    if not names or any(wanted.lower() in (fam.lower(), full.lower()) for fam, full in names):
        return wanted
    return names[0][1]


def prepare_job_fonts(job_dir):
    """libass reads fonts from a folder next to the captions (avoids Windows path issues)."""
    dst = Path(job_dir) / "fonts"
    dst.mkdir(exist_ok=True)
    if FONTS_DIR.exists():
        for f in FONTS_DIR.iterdir():
            if f.suffix.lower() in (".ttf", ".otf") and not (dst / f.name).exists():
                shutil.copy(f, dst / f.name)
    if not any(f.suffix.lower() in (".ttf", ".otf") for f in dst.iterdir()):
        fallback = find_font_file()  # e.g. Arial Bold on a Mac
        if fallback:
            shutil.copy(fallback, dst / Path(fallback).name)
