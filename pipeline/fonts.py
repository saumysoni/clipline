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


def caption_font_name(job_fonts=None):
    """Family name libass should use for burned-in captions.

    Uses CAPTION_FONT when that font is in the fonts folder; otherwise the font that is
    there, so captions never come out in a missing font (or not at all).
    """
    wanted = os.getenv("CAPTION_FONT", "Montserrat ExtraBold")
    if not job_fonts or not Path(job_fonts).exists():
        return wanted
    families = [f for f in (font_family(p) for p in sorted(Path(job_fonts).iterdir())
                            if p.suffix.lower() in (".ttf", ".otf")) if f]
    if not families or wanted.lower() in (f.lower() for f in families):
        return wanted
    return families[0]


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
