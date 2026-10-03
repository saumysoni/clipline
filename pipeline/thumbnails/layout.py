"""
Thumbnails, step 4: drawing the collage on a 1080x1920 canvas (sticker outlines, photo cards,
sunburst background, text), kept under YouTube's 2 MB limit.
"""
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from pipeline.constants import OUT_H, OUT_W
from pipeline.fonts import find_font_file
from pipeline.text import without_emoji
from pipeline.thumbnails.cutout import crop_box, cut_out, face_cutout, face_size


W, H = OUT_W, OUT_H


MAX_BYTES = 2 * 1024 * 1024  # YouTube's thumbnail size limit


def hex_rgb(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def scale_to(img, max_w, max_h):
    s = min(max_w / img.width, max_h / img.height)
    return img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.LANCZOS)


def sticker(rgba, outline, color, glow=0):
    """Thick outline around a cut-out (like a sticker), with an optional neon glow."""
    pad = outline + glow * 2 + 8
    canvas = Image.new("RGBA", (rgba.width + 2 * pad, rgba.height + 2 * pad), (0, 0, 0, 0))
    a = Image.new("L", canvas.size, 0)
    a.paste(rgba.getchannel("A"), (pad, pad))
    grown = a.filter(ImageFilter.GaussianBlur(outline / 2)).point(lambda v: 255 if v > 6 else 0)
    grown = grown.filter(ImageFilter.GaussianBlur(1))
    if glow:
        halo = grown.filter(ImageFilter.GaussianBlur(glow)).point(lambda v: min(255, int(v * 1.6)))
        canvas.paste(Image.new("RGBA", canvas.size, color + (255,)), (0, 0), halo)
    canvas.paste(Image.new("RGBA", canvas.size, color + (255,)), (0, 0), grown)
    canvas.alpha_composite(rgba, (pad, pad))
    return canvas


def photo_card(img, size, border=18):
    """A white-bordered photo, like a print pinned to a vision board."""
    card = scale_to(img, size, size)
    framed = Image.new("RGBA", (card.width + 2 * border, card.height + 2 * border), (255, 255, 255, 255))
    framed.paste(card, (border, border))
    mask = Image.new("L", framed.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, framed.width - 1, framed.height - 1), radius=22, fill=255)
    framed.putalpha(mask)
    return framed


def with_shadow(rgba, angle=0, blur=14, offset=(10, 16), opacity=150):
    rot = rgba.rotate(angle, resample=Image.BICUBIC, expand=True)
    pad = blur * 3
    out = Image.new("RGBA", (rot.width + 2 * pad, rot.height + 2 * pad), (0, 0, 0, 0))
    sh = Image.new("RGBA", out.size, (0, 0, 0, 0))
    alpha = rot.getchannel("A").point(lambda v: v * opacity // 255)
    sh.paste(Image.new("RGBA", rot.size, (0, 0, 0, 255)), (pad + offset[0], pad + offset[1]), alpha)
    out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(blur)))
    out.alpha_composite(rot, (pad, pad))
    return out


def place(canvas, rgba, cx, cy):
    canvas.alpha_composite(rgba, (int(cx - rgba.width / 2), int(cy - rgba.height / 2)))


def background(img, accent, blur=26, rays=True):
    """The frame itself, blurred, darkened and tinted: busy enough to feel real, calm enough for text."""
    s = max(W / img.width, H / img.height)
    big = img.resize((int(img.width * s) + 1, int(img.height * s) + 1), Image.LANCZOS)
    l, t = (big.width - W) // 2, (big.height - H) // 2
    bg = big.crop((l, t, l + W, t + H)).filter(ImageFilter.GaussianBlur(blur))
    bg = ImageEnhance.Brightness(ImageEnhance.Color(bg).enhance(1.35)).enhance(0.55).convert("RGBA")
    tint = Image.new("RGBA", (W, H), accent + (0,))
    grad = Image.linear_gradient("L").resize((W, H)).point(lambda v: int(v * 0.35))
    tint.putalpha(grad.transpose(Image.FLIP_TOP_BOTTOM))
    bg.alpha_composite(tint)
    if rays:
        bg.alpha_composite(sunburst(accent, (W // 2, int(H * 0.62))))
    ramp = Image.linear_gradient("L").resize((W, H))
    top = ramp.transpose(Image.FLIP_TOP_BOTTOM).point(lambda v: int(max(0, v - 150) * 1.9))
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shade.putalpha(top)
    bg.alpha_composite(shade)  # darker at the top, where the text goes
    return bg


def sunburst(color, centre, rays=18, opacity=70):
    """Comic-style rays of light behind the face, in the accent colour."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = centre
    r = 2 * H
    step = 2 * np.pi / rays
    for k in range(0, rays, 2):
        a0, a1 = k * step, (k + 1) * step
        d.polygon([(cx, cy), (cx + r * np.cos(a0), cy + r * np.sin(a0)), (cx + r * np.cos(a1), cy + r * np.sin(a1))],
                  fill=color + (opacity,))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((cx - 420, cy - 420, cx + 420, cy + 420), fill=color + (120,))
    layer.alpha_composite(glow.filter(ImageFilter.GaussianBlur(160)))
    return layer.filter(ImageFilter.GaussianBlur(3))


def font(size):
    path = find_font_file()
    return ImageFont.truetype(path, size) if path else ImageFont.load_default()


def fit_font(draw, text, max_size, max_w):
    size = max_size
    while size > 48:
        f = font(size)
        if draw.textlength(text, font=f) <= max_w:
            return f
        size -= 6
    return font(size)


def draw_text(canvas, line1, line2, accent, top=110):
    """Line 1 in white, line 2 on an accent-coloured block, centred at the top (away from the face)."""
    d = ImageDraw.Draw(canvas)
    l1, l2 = without_emoji(line1).upper().strip(), without_emoji(line2).upper().strip()
    y = top
    if l1:
        f1 = fit_font(d, l1, 130, W - 140)
        tw = d.textlength(l1, font=f1)
        d.text(((W - tw) / 2, y), l1, font=f1, fill="white", stroke_width=11, stroke_fill="black")
        y += f1.size + 34
    if l2:
        f2 = fit_font(d, l2, 160, W - 170)
        tw = d.textlength(l2, font=f2)
        x = (W - tw) / 2
        box = (x - 32, y - 12, x + tw + 32, y + f2.size + 34)
        shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle(tuple(v + o for v, o in zip(box, (8, 12, 8, 12))),
                                                 radius=26, fill=(0, 0, 0, 160))
        canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(10)))
        d = ImageDraw.Draw(canvas)
        d.rounded_rectangle(box, radius=26, fill=accent)
        d.text((x, y), l2, font=f2, fill=(17, 17, 17))
        y = box[3]
    return y


def draw_text_keyword(canvas, line1, line2, accent, top=100, line2_fill=None):
    """Line 1 in white, line 2 bigger in the accent colour (the keyword), both with a heavy black outline
    and a soft shadow: the common creator style, no boxes."""
    l1, l2 = without_emoji(line1).upper().strip(), without_emoji(line2).upper().strip()
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sd, d = ImageDraw.Draw(shadow), ImageDraw.Draw(canvas)
    y, lines = top, []
    if l1:
        f1 = fit_font(d, l1, 140, W - 120)
        lines.append((l1, f1, (255, 255, 255), y)); y += f1.size + 18
    if l2:
        f2 = fit_font(d, l2, 190, W - 110)
        lines.append((l2, f2, line2_fill or accent, y)); y += f2.size + 18
    for text, f, fill, ly in lines:
        x = (W - d.textlength(text, font=f)) / 2
        sd.text((x + 6, ly + 10), text, font=f, fill=(0, 0, 0, 200), stroke_width=14, stroke_fill=(0, 0, 0, 200))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(9)))
    d = ImageDraw.Draw(canvas)
    for text, f, fill, ly in lines:
        x = (W - d.textlength(text, font=f)) / 2
        d.text((x, ly), text, font=f, fill=fill, stroke_width=14, stroke_fill="black")
    return y


def circle_badge(img, size, ring=(255, 255, 255), ring_w=14):
    """A round photo badge (centre square of `img`) with a thick ring."""
    side = min(img.size)
    sq = img.crop(((img.width - side) // 2, (img.height - side) // 2,
                   (img.width + side) // 2, (img.height + side) // 2)).convert("RGB").resize((size, size), Image.LANCZOS)
    out = Image.new("RGBA", (size + 2 * ring_w, size + 2 * ring_w), (0, 0, 0, 0))
    m = Image.new("L", out.size, 0)
    ImageDraw.Draw(m).ellipse((0, 0, out.width - 1, out.height - 1), fill=255)
    out.paste(Image.new("RGBA", out.size, ring + (255,)), (0, 0), m)
    inner = Image.new("L", (size, size), 0)
    ImageDraw.Draw(inner).ellipse((0, 0, size - 1, size - 1), fill=255)
    out.paste(sq, (ring_w, ring_w), inner)
    return out


def graded_background(img, accent, blur=10):
    """The real location as the background: filled to 9:16, softly blurred, punchier colour and
    contrast, a vignette, and darker at the top for the text."""
    s = max(W / img.width, H / img.height)
    big = img.resize((int(img.width * s) + 1, int(img.height * s) + 1), Image.LANCZOS)
    l, t = (big.width - W) // 2, (big.height - H) // 2
    bg = big.crop((l, t, l + W, t + H)).filter(ImageFilter.GaussianBlur(blur))
    bg = ImageEnhance.Contrast(ImageEnhance.Color(bg).enhance(1.3)).enhance(1.15)
    bg = ImageEnhance.Brightness(bg).enhance(0.85).convert("RGBA")
    vignette = Image.new("L", (W, H), 0)
    ImageDraw.Draw(vignette).ellipse((-W * 0.35, -H * 0.15, W * 1.35, H * 1.15), fill=255)
    dark = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dark.putalpha(vignette.filter(ImageFilter.GaussianBlur(160)).point(lambda v: int((255 - v) * 0.75)))
    bg.alpha_composite(dark)
    top = Image.linear_gradient("L").resize((W, H)).transpose(Image.FLIP_TOP_BOTTOM).point(lambda v: int(max(0, v - 140) * 1.6))
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shade.putalpha(top)
    bg.alpha_composite(shade)
    return bg


def gradient_background(accent):
    """A smooth vertical gradient from a deep shade of the accent to the accent, with a soft light
    behind where the head goes."""
    top_c = tuple(int(c * 0.22) for c in accent)
    bot_c = tuple(int(c * 0.75) for c in accent)
    ramp = Image.linear_gradient("L").resize((W, H))
    bg = Image.composite(Image.new("RGB", (W, H), bot_c), Image.new("RGB", (W, H), top_c), ramp).convert("RGBA")
    light = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(light).ellipse((W * 0.5 - 520, H * 0.5 - 520, W * 0.5 + 520, H * 0.5 + 520), fill=(255, 255, 255, 70))
    bg.alpha_composite(light.filter(ImageFilter.GaussianBlur(170)))
    return bg


# collage slots (centre x, centre y, size, tilt) for 1-3 items. With a face, the items sit in the
# middle band around the head; the face sticker fills the bottom; the text is at the top.
SLOTS_WITH_FACE = {1: [(790, 760, 520, 7)],
                   2: [(250, 720, 470, -8), (830, 800, 470, 7)],
                   3: [(240, 680, 430, -8), (840, 700, 430, 7), (200, 1120, 360, -5)]}


SLOTS_NO_FACE = {1: [(540, 1120, 940, -3)],
                 2: [(360, 900, 660, -6), (720, 1380, 660, 5)],
                 3: [(330, 820, 580, -7), (760, 1140, 580, 6), (360, 1480, 540, -4)]}


MAX_UPSCALE = 2.2   # a collage piece is never blown up more than this (more looks blurry)
MIN_PIECE = 230     # pixels: a piece that would have to be smaller than this is left out
FACE_TRIES = 3      # frames tried for the face cut-out (the AI's choice first, then the biggest faces)
MIN_FACE_CARD = 0.15  # face width / frame width needed to show the face as a framed photo instead


def pick_face(frames, first, face_box=None, person_box=None):
    """(cut-out, None) of the creator, or (None, framed-photo crop) if no cut-out worked but a face is
    big enough to show as a photo, or (None, None): then the thumbnail goes without a face.
    The AI's frame (with its face_box) is tried first, then the frames with the biggest faces."""
    sizes = [face_size(f) for f in frames]
    if face_box:
        sizes[first] = (face_box[3] - face_box[1]) / 1000
    order = [first] + sorted((k for k in range(len(frames)) if k != first and sizes[k] > 0),
                             key=lambda k: -sizes[k])
    tried, backup = [], None
    for k in order[:FACE_TRIES]:
        cut, crop, info = face_cutout(frames[k], *((face_box, person_box) if k == first else (None, None)))
        if cut is not None and ("top" not in info["sides"] or (k == first and face_box)):
            # (the AI's own frame wins even with someone right above: the face finder's guesses for
            #  other frames can be wrong, e.g. a "face" on a wall)
            return (cut, info), None
        if cut is not None and backup is None:  # someone right above the creator: only if nothing better
            backup = (cut, info)
        tried.append((sizes[k], crop))
    if backup:
        return backup, None
    big = [crop for size, crop in tried if size >= MIN_FACE_CARD]
    return None, (big[0] if big else None)


def place_person(canvas, cut, info, accent, face_x=0.5, head_top=0.30, height=0.62, outline=24, glow=30,
                 color=None, shadow=False):
    """The creator as a big sticker rising from the bottom, face near `face_x` (share of the width).
    Straight cut edges (info["sides"]) are pushed past the canvas edges by making the creator bigger,
    never by sliding the face off to one side, so the outline only follows the creator's real shape.
    The head starts no higher than `head_top` (share of the height) to leave room for the text."""
    sides, (fx, fy, fw, fh) = info["sides"], info["face"]
    over = outline + 10  # how far a straight edge must go past the canvas edge
    cx = fx + fw / 2
    s_ = H * height / cut.height
    if "left" in sides:
        s_ = max(s_, (W * face_x + over) / max(1, cx))
    if "right" in sides:
        s_ = max(s_, (W * (1 - face_x) + over) / max(1, cut.width - cx))
    s_ = min(s_, W * 0.55 / fw)  # never a face wider than 55% of the thumbnail
    person = cut.resize((max(1, int(cut.width * s_)), max(1, int(cut.height * s_))), Image.LANCZOS)
    art = sticker(person, outline=outline, color=color or accent, glow=glow)
    pad = outline + glow * 2 + 8  # sticker() adds this much around the person
    x = W * face_x - cx * s_ - pad
    y = max(H * head_top, H - person.height + over) - pad
    if shadow:  # a soft dark shadow behind the person instead of a glow
        sh = Image.new("RGBA", art.size, (0, 0, 0, 0))
        sh.paste(Image.new("RGBA", art.size, (0, 0, 0, 170)), (0, 0), art.getchannel("A"))
        canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(22)), (int(x + 14), int(y + 22)))
    canvas.alpha_composite(art, (int(x), int(y)))
    # where the face ended up on the canvas (left, top, right, bottom), so pieces can stay off it
    return (x + pad + fx * s_, y + pad + fy * s_, x + pad + (fx + fw) * s_, y + pad + (fy + fh) * s_)


def piece_size(img, slot):
    """How big a collage piece can be drawn without blowing it up too much (0: leave it out)."""
    size = min(slot, int(max(img.size) * MAX_UPSCALE))
    return size if size >= MIN_PIECE else 0


LOOKS = ("burst", "scene", "bold")


def prepare(frames, pl, largest_slot):
    """Everything a look needs, worked out once: the creator's cut-out (or a framed photo), the collage
    pieces that are sharp enough at `largest_slot` pixels, and the frames for the background."""
    person, face_crop = (pick_face(frames, pl["face_frame"], pl.get("face_box"), pl.get("person_box"))
                         if pl["face_frame"] is not None else (None, None))
    pieces = []
    for it in pl["items"]:
        crop = crop_box(frames[it["frame"]], it["box"])
        cut = cut_out(crop) if it["kind"] == "object" else None
        piece = ("cut", cut) if cut is not None else ("card", crop)
        if piece_size(piece[1], largest_slot):  # too small to show sharply: leave it out
            pieces.append(piece)
    scene = next((frames[it["frame"]] for it in pl["items"] if it["kind"] == "scene"), None)
    face_frame = frames[pl["face_frame"]] if pl["face_frame"] is not None else None
    # a frame with as little face in it as possible, for backgrounds (no blurry "ghost" of the creator)
    quiet = min(frames, key=face_size)
    return {"accent": hex_rgb(pl["accent"]), "person": person, "face_crop": face_crop, "pieces": pieces,
            "scene": scene, "face_frame": face_frame, "quiet_frame": quiet, "any_frame": frames[0]}


def compose(frames, pl):
    """The thumbnail in the look saved in the plan (or THUMB_LOOK in .env, default scene). Each look is
    its own file in looks/; they share the cut-outs and drawing helpers here."""
    import importlib

    look = pl.get("look") or os.getenv("THUMB_LOOK", "scene").strip().lower()
    if look not in LOOKS:
        look = "scene"
    pl["look"] = look
    return importlib.import_module(f"pipeline.thumbnails.looks.{look}").render(frames, pl)


def save(img, path):
    for q in (92, 86, 80, 72):
        img.save(path, "JPEG", quality=q, optimize=True)
        if Path(path).stat().st_size <= MAX_BYTES:
            return
