"""
Thumbnails, step 3: drawing on a 1080x1920 canvas. Shared helpers (crop to 9:16 around what matters,
colour grade, creator-style text) and compose(), which hands the plan to looks/<look>.py.
Output stays under YouTube's 2 MB thumbnail limit.
"""
import importlib
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from pipeline.constants import OUT_H, OUT_W
from pipeline.fonts import find_font_file
from pipeline.text import without_emoji


W, H = OUT_W, OUT_H


MAX_BYTES = 2 * 1024 * 1024  # YouTube's thumbnail size limit


LOOKS = ("frame", "duotone")  # one file each in looks/; the first is the default


def hex_rgb(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


# ------------------------------------------------------------------ the picture
ZOOM = 1.12      # crop a little tighter than the full frame height, so the face can be moved under the text
FACE_AT = 0.56   # where the subject's centre goes, as a share of the height (the text sits above it)


def portrait(img, focus=None, w=W, h=H):
    """A 9:16 crop of `img` scaled to w x h, with `focus` (box_2d [ymin, xmin, ymax, xmax] on a 0-1000
    scale, usually the creator's face) centred across and placed at FACE_AT down the picture."""
    cx, cy = 0.5, 0.42
    if focus:
        cy, cx = (focus[0] + focus[2]) / 2000, (focus[1] + focus[3]) / 2000
    ch = min(img.height, round(img.height / ZOOM))
    cw = min(img.width, round(ch * w / h))
    ch = round(cw * h / w)
    left = min(max(0, round(cx * img.width - cw / 2)), img.width - cw)
    top = min(max(0, round(cy * img.height - ch * FACE_AT)), img.height - ch)
    out = img.crop((left, top, left + cw, top + ch)).resize((w, h), Image.LANCZOS)
    if cw < w * 0.7:  # blown up a lot (a low-resolution vlog): sharpen the edges back a little
        out = out.filter(ImageFilter.UnsharpMask(3, 70, 2))
    return out


def subject_span(img, focus=None):
    """(top, bottom) of the focus box in portrait()'s picture, as shares of the height."""
    if not focus:
        return FACE_AT - 0.1, FACE_AT + 0.1
    cy = (focus[0] + focus[2]) / 2000
    ch = min(img.height, round(img.height / ZOOM))
    ch = round(min(img.width, round(ch * W / H)) * H / W)
    top = min(max(0, round(cy * img.height - ch * FACE_AT)), img.height - ch)
    return ((focus[0] / 1000 * img.height - top) / ch, (focus[2] / 1000 * img.height - top) / ch)


def grade(img, sat=1.2, con=1.1, bright=1.0):
    img = ImageEnhance.Color(img).enhance(sat)
    img = ImageEnhance.Contrast(img).enhance(con)
    return ImageEnhance.Brightness(img).enhance(bright) if bright != 1 else img


def shade(canvas, at_top=True, strength=210):
    """A soft dark gradient where the text goes, so white text reads on any picture."""
    ramp = Image.linear_gradient("L").resize((W, H))
    if at_top:
        ramp = ramp.transpose(Image.FLIP_TOP_BOTTOM)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    layer.putalpha(ramp.point(lambda v: int(max(0, v - 115) / 140 * strength)))
    canvas.alpha_composite(layer)


# ------------------------------------------------------------------ text
# Thumbnail fonts, bundled (SIL Open Font License, see fonts/OFL-*.txt), in the style creators use:
# a tall, condensed, heavy headline (Anton) and a classy serif for the small line (DM Serif Display).
# They cover Latin letters only; other scripts fall back to the system's bold font.
FONTS = Path(__file__).parent / "fonts"
FONT_FILES = {"head": FONTS / "Anton-Regular.ttf", "kicker": FONTS / "DMSerifDisplay-Regular.ttf"}


def font(size, kind="head", text=""):
    path = FONT_FILES.get(kind)
    if not path or not path.exists() or any(ord(c) > 0x24F for c in text):
        path = find_font_file()
    return ImageFont.truetype(str(path), size) if path else ImageFont.load_default()


def fit_font(draw, text, max_size, max_w, kind="head", min_size=48):
    size = max_size
    while size > min_size:
        f = font(size, kind, text)
        if draw.textlength(text, font=f) <= max_w:
            return f
        size -= 6
    return font(size, kind, text)


def text_lines(draw, line1, line2, scale=1.0):
    """[(text, font, y offset, stroke)] for a small serif line and a huge condensed headline (split in
    two lines when one line would have to be small), and the total height."""
    l1, l2 = without_emoji(line1).strip().upper(), without_emoji(line2).strip().upper()
    lines, y = [], 0
    if l1:
        f1 = fit_font(draw, l1, int(104 * scale), W - 200, "kicker", int(48 * scale))
        lines.append((l1, f1, y, 3)); y += int(f1.size * 1.12)
    if l2:
        f2 = fit_font(draw, l2, int(300 * scale), W - 110, "head", int(110 * scale))
        parts = [l2]
        if f2.size < 170 * scale and " " in l2:  # long headline: two lines read bigger than one squeezed line
            words = l2.split()
            half = max(1, len(words) // 2)
            parts = [" ".join(words[:half]), " ".join(words[half:])]
            f2 = min((fit_font(draw, t, int(260 * scale), W - 110, "head", int(110 * scale)) for t in parts),
                     key=lambda f: f.size)
        for t in parts:
            lines.append((t, f2, y - int(f2.size * 0.08), 5)); y += int(f2.size * 1.08)
    return lines, y


TEXT_TOP = 90       # pixels from the top for text at the top
TEXT_BOTTOM = 230   # pixels kept clear at the bottom (YouTube draws the title over it)
GAP = 30            # pixels between the text and the face


def text_spot(canvas, line1, line2, span):
    """Where the text goes: (at_top, scale). At the top if it fits above the face, else at the bottom if it
    fits below; otherwise on whichever side has more room, made smaller to fit (never below half size)."""
    d = ImageDraw.Draw(canvas)
    _, height = text_lines(d, line1, line2)
    above = span[0] * H - TEXT_TOP - GAP
    below = H - TEXT_BOTTOM - span[1] * H - GAP
    if height <= above:
        return True, 1.0
    if height <= below:
        return False, 1.0
    room = max(above, below)
    return above >= below, max(0.5, min(1.0, room / max(1, height)))


def draw_text(canvas, line1, line2, at_top=True, scale=1.0):
    """The creator style from real channels: a small serif line, then a huge condensed headline, both
    plain white with a soft shadow (no boxes), at the top or the bottom (see text_spot())."""
    d = ImageDraw.Draw(canvas)
    lines, height = text_lines(d, line1, line2, scale)
    top = TEXT_TOP if at_top else H - height - TEXT_BOTTOM
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    for text, f, ly, stroke in lines:
        x = (W - d.textlength(text, font=f)) / 2
        sd.text((x + 4, top + ly + 8), text, font=f, fill=(0, 0, 0, 210), stroke_width=stroke + 8,
                stroke_fill=(0, 0, 0, 210))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(12)))
    d = ImageDraw.Draw(canvas)
    for text, f, ly, stroke in lines:
        x = (W - d.textlength(text, font=f)) / 2
        d.text((x, top + ly), text, font=f, fill="white", stroke_width=stroke, stroke_fill=(20, 20, 20))
    return top + height


def add_text(canvas, img, pl, shade_strength=210):
    """Shade and text for a look drawn from `img` with portrait(img, pl["focus"]), kept off the face."""
    at_top, scale = text_spot(canvas, pl.get("line1", ""), pl.get("line2", ""), subject_span(img, pl.get("focus")))
    shade(canvas, at_top=at_top, strength=shade_strength)
    draw_text(canvas, pl.get("line1", ""), pl.get("line2", ""), at_top, scale)


# ------------------------------------------------------------------ putting it together
def compose(frames, pl):
    """The thumbnail in the look saved in the plan (or THUMB_LOOK in .env, default frame)."""
    look = pl.get("look") or os.getenv("THUMB_LOOK", LOOKS[0]).strip().lower()
    if look not in LOOKS:  # plans from before (scene, burst, bold) are redrawn as frame
        look = LOOKS[0]
    pl["look"] = look
    return importlib.import_module(f"pipeline.thumbnails.looks.{look}").render(frames, pl)


def save(img, path):
    for q in (92, 86, 80, 72):
        img.save(path, "JPEG", quality=q, optimize=True)
        if Path(path).stat().st_size <= MAX_BYTES:
            return
