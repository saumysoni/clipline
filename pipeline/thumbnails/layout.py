"""
Thumbnails, step 4: drawing the collage on a 1080x1920 canvas (sticker outlines, photo cards,
sunburst background, text), kept under YouTube's 2 MB limit.
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from pipeline.constants import OUT_H, OUT_W
from pipeline.fonts import find_font_file
from pipeline.text import without_emoji
from pipeline.thumbnails.cutout import crop_box, cut_out, face_cutout


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


def background(img, accent, blur=26):
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


# collage slots (centre x, centre y, size, tilt) for 1-3 items. With a face, the items sit in the
# middle band around the head; the face sticker fills the bottom; the text is at the top.
SLOTS_WITH_FACE = {1: [(790, 760, 520, 7)],
                   2: [(250, 720, 470, -8), (830, 800, 470, 7)],
                   3: [(240, 680, 430, -8), (840, 700, 430, 7), (200, 1120, 360, -5)]}


SLOTS_NO_FACE = {1: [(540, 1120, 940, -3)],
                 2: [(360, 900, 660, -6), (720, 1380, 660, 5)],
                 3: [(330, 820, 580, -7), (760, 1140, 580, 6), (360, 1480, 540, -4)]}


def compose(frames, pl):
    accent = hex_rgb(pl["accent"])
    face_img = frames[pl["face_frame"]] if pl["face_frame"] is not None else None
    face_cut, face_crop = face_cutout(face_img) if face_img is not None else (None, None)

    pieces = []
    for it in pl["items"]:
        crop = crop_box(frames[it["frame"]], it["box"])
        cut = cut_out(crop) if it["kind"] == "object" else None
        pieces.append(("cut", cut) if cut is not None else ("card", crop))
    if face_img is None and not pieces:
        raise RuntimeError("nothing to put on the thumbnail")

    scene = next((frames[it["frame"]] for it in pl["items"] if it["kind"] == "scene"), None)
    if scene is not None:
        canvas = background(scene, accent)
    elif face_img is not None:
        canvas = background(face_img, accent, blur=70)  # heavy blur: no ghost of the face
    else:
        canvas = background(frames[pl["items"][0]["frame"]], accent)

    have_face = face_img is not None
    slots = (SLOTS_WITH_FACE if have_face else SLOTS_NO_FACE).get(len(pieces), [])
    for (kind, img), (cx, cy, size, tilt) in zip(pieces, slots):
        if kind == "cut":
            art = sticker(scale_to(img, size, size), outline=16, color=(255, 255, 255))
        else:
            art = photo_card(img, size)
        place(canvas, with_shadow(art, tilt), cx, cy)

    if have_face:
        if face_cut is not None:
            target_h = H * 0.60
            s_ = min(target_h / face_cut.height, W * 1.15 / face_cut.width)
            face = face_cut.resize((int(face_cut.width * s_), int(face_cut.height * s_)), Image.LANCZOS)
            art = sticker(face, outline=24, color=accent, glow=30)
            pad = 24 + 60 + 8
            canvas.alpha_composite(art, (int((W - art.width) / 2), int(H - art.height + pad)))
        else:  # the cut-out didn't work: show the face as a big framed photo instead
            art = with_shadow(photo_card(face_crop, 820, border=24), -3)
            place(canvas, art, W // 2, int(H * 0.70))

    draw_text(canvas, pl["line1"], pl["line2"], accent)
    return canvas.convert("RGB")


def save(img, path):
    for q in (92, 86, 80, 72):
        img.save(path, "JPEG", quality=q, optimize=True)
        if Path(path).stat().st_size <= MAX_BYTES:
            return
