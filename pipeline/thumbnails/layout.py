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
from pipeline.thumbnails.cutout import crop_box, cut_out, face_cutout, face_size, resize_cutout


W, H = OUT_W, OUT_H


MAX_BYTES = 2 * 1024 * 1024  # YouTube's thumbnail size limit


def hex_rgb(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def scale_to(img, max_w, max_h):
    s = min(max_w / img.width, max_h / img.height)
    if img.mode == "RGBA":  # a cut-out: keep its edge crisp and smooth at the new size
        return resize_cutout(img, img.width * s, img.height * s)
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


def draw_text(canvas, line1, line2, accent, top=90):
    """The creator style from real channels: a small serif line, then a huge condensed headline, both
    plain white with a soft shadow (no boxes)."""
    l1, l2 = without_emoji(line1).strip(), without_emoji(line2).upper().strip()
    d = ImageDraw.Draw(canvas)
    lines, y = [], top
    if l1:
        f1 = fit_font(d, l1.upper(), 104, W - 200, "kicker")
        lines.append((l1.upper(), f1, y, 3)); y += int(f1.size * 1.12)
    if l2:
        f2 = fit_font(d, l2, 300, W - 110, "head", 110)
        if f2.size < 170 and " " in l2:  # long headline: two lines read bigger than one squeezed line
            words = l2.split()
            half = max(1, len(words) // 2)
            parts = [" ".join(words[:half]), " ".join(words[half:])]
            f2 = min((fit_font(d, t, 260, W - 110, "head", 110) for t in parts), key=lambda f: f.size)
        else:
            parts = [l2]
        for t in parts:
            lines.append((t, f2, y - int(f2.size * 0.08), 5)); y += int(f2.size * 1.08)
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    for text, f, ly, stroke in lines:
        x = (W - d.textlength(text, font=f)) / 2
        sd.text((x + 4, ly + 8), text, font=f, fill=(0, 0, 0, 210), stroke_width=stroke + 8, stroke_fill=(0, 0, 0, 210))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(12)))
    d = ImageDraw.Draw(canvas)
    for text, f, ly, stroke in lines:
        x = (W - d.textlength(text, font=f)) / 2
        d.text((x, ly), text, font=f, fill="white", stroke_width=stroke, stroke_fill=(20, 20, 20))
    return y


def draw_text_keyword(canvas, line1, line2, accent, top=100, line2_fill=None):
    """Line 1 in white, line 2 bigger in the accent colour (the keyword), both with a heavy black outline
    and a soft shadow: the common creator style, no boxes."""
    l1, l2 = without_emoji(line1).upper().strip(), without_emoji(line2).upper().strip()
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sd, d = ImageDraw.Draw(shadow), ImageDraw.Draw(canvas)
    y, lines = top, []
    if l1:
        f1 = fit_font(d, l1, 150, W - 120)
        lines.append((l1, f1, (255, 255, 255), y)); y += f1.size + 18
    if l2:
        f2 = fit_font(d, l2, 240, W - 110)
        lines.append((l2, f2, line2_fill or accent, y)); y += f2.size + 18
    for text, f, fill, ly in lines:
        x = (W - d.textlength(text, font=f)) / 2
        sd.text((x + 6, ly + 10), text, font=f, fill=(0, 0, 0, 200), stroke_width=16, stroke_fill=(0, 0, 0, 200))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(9)))
    d = ImageDraw.Draw(canvas)
    for text, f, fill, ly in lines:
        x = (W - d.textlength(text, font=f)) / 2
        d.text((x, ly), text, font=f, fill=fill, stroke_width=9, stroke_fill="black")
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


SHAPES = ("circle", "rounded", "arch", "polaroid")


def shaped_card(img, size, shape, ring=(255, 255, 255), ring_w=12):
    """A photo in a shape, with a white rim: "circle", "rounded" (square), "arch" (tall, round top) or
    "polaroid" (white frame, thicker at the bottom). Mixing shapes makes the collage feel hand-made."""
    if shape == "circle":
        return circle_badge(img, size, ring, ring_w)
    if shape == "polaroid":
        side = min(img.size)
        sq = img.crop(((img.width - side) // 2, (img.height - side) // 2,
                       (img.width + side) // 2, (img.height + side) // 2)).convert("RGB").resize((size, size), Image.LANCZOS)
        b = max(10, size // 22)
        out = Image.new("RGBA", (size + 2 * b, size + 5 * b), (255, 255, 255, 255))
        out.paste(sq, (b, b))
        return out
    w, h = (size, size) if shape == "rounded" else (int(size * 0.78), size)
    s_ = max(w / img.width, h / img.height)
    big = img.convert("RGB").resize((max(w, int(img.width * s_) + 1), max(h, int(img.height * s_) + 1)), Image.LANCZOS)
    l, t = (big.width - w) // 2, (big.height - h) // 2
    photo = big.crop((l, t, l + w, t + h))
    out = Image.new("RGBA", (w + 2 * ring_w, h + 2 * ring_w), (0, 0, 0, 0))

    def outline(draw, box):
        if shape == "rounded":
            draw.rounded_rectangle(box, radius=int(min(w, h) * 0.16), fill=255)
        else:  # arch: half circle on top of a rectangle with slightly rounded bottom corners
            x0, y0, x1, y1 = box
            r = (x1 - x0) / 2
            draw.ellipse((x0, y0, x1, y0 + 2 * r), fill=255)
            draw.rounded_rectangle((x0, y0 + r, x1, y1), radius=int(r * 0.25), fill=255)

    m = Image.new("L", out.size, 0)
    outline(ImageDraw.Draw(m), (0, 0, out.width - 1, out.height - 1))
    out.paste(Image.new("RGBA", out.size, ring + (255,)), (0, 0), m)
    inner = Image.new("L", (w, h), 0)
    outline(ImageDraw.Draw(inner), (0, 0, w - 1, h - 1))
    out.paste(photo, (ring_w, ring_w), inner)
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


# collage slots (centre x, centre y, size, tilt). With a face, up to 6 pieces surround the creator, who
# is the biggest thing; the text is at the top. The first slots are the biggest and go
# to the things the AI picked; the rest is filled with other moments from the Short.
SLOTS_AROUND_FACE = [(205, 700, 380, -8), (875, 720, 380, 7), (130, 1180, 290, 5), (950, 1200, 290, -6),
                     (150, 1600, 300, -4), (930, 1640, 300, 6)]
BEHIND = 2  # the first slots sit behind the creator (beside the head); the lower ones overlap her edges


# without a face: the main thing big in the middle, the others around it
SLOTS_NO_FACE = [(540, 1130, 820, -3), (210, 700, 360, -7), (870, 720, 360, 6), (190, 1620, 360, 5),
                 (890, 1640, 360, -5)]


MAX_UPSCALE = 2.2   # a collage piece is never blown up more than this (more looks blurry)
MIN_PIECE = 230     # pixels: a piece that would have to be smaller than this is left out
FACE_TRIES = 3      # frames tried for the face cut-out (the AI's choice first, then the biggest faces)
MIN_FACE_CARD = 0.15  # face width / frame width needed to show the face as a framed photo instead


def pick_face(frames, first, face_box=None, person_box=None):
    """(cut-out, None) of the creator, or (None, framed-photo crop) if no cut-out worked but a face is
    big enough to show as a photo, or (None, None): then the thumbnail goes without a face.
    The AI's frame (with its face_box) is tried first, then the frames with the biggest faces."""
    sizes = {first: (face_box[3] - face_box[1]) / 1000 if face_box else face_size(frames[first])}

    def order():  # the AI's frame first; the face finder only runs on the others if that one fails
        yield first
        for k in range(len(frames)):
            if k != first:
                sizes[k] = face_size(frames[k])
        yield from sorted((k for k in sizes if k != first and sizes[k] > 0), key=lambda k: -sizes[k])

    tried, backup = [], None
    for n, k in enumerate(order()):
        if n >= FACE_TRIES:
            break
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
                 color=None, shadow=False, max_face=0.55):
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
    s_ = min(s_, W * max_face / fw)  # never a face wider than this share of the thumbnail (default 55%)
    person = resize_cutout(cut, cut.width * s_, cut.height * s_)
    art = sticker(person, outline=outline, color=color or accent, glow=glow)
    pad = outline + glow * 2 + 8  # sticker() adds this much around the person
    # If the size cap kept a straight edge (an arm cut off by the camera frame) inside the thumbnail,
    # slide the creator toward that side until it's past the edge, within reason.
    left_x = W * face_x - cx * s_
    if "left" in sides and "right" not in sides and left_x > -over:
        face_x = max(0.24, face_x - (left_x + over) / W)
    elif "right" in sides and "left" not in sides and left_x + person.width < W + over:
        face_x = min(0.76, face_x + (W + over - left_x - person.width) / W)
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


def prepare(frames, pl, largest_slot, fill=0):
    """Everything a look needs, worked out once: the creator's cut-out (or a framed photo), the collage
    pieces that are sharp enough at `largest_slot` pixels, and the frames for the background.
    fill: add other moments of the Short as extra photo pieces until there are this many pieces."""
    person, face_crop = (pick_face(frames, pl["face_frame"], pl.get("face_box"), pl.get("person_box"))
                         if pl["face_frame"] is not None else (None, None))
    pieces = []
    for it in pl["items"]:
        crop = crop_box(frames[it["frame"]], it["box"])
        cut = cut_out(crop) if it["kind"] == "object" else None
        piece = ("cut", cut) if cut is not None else ("card", crop)
        if piece_size(piece[1], largest_slot):  # too small to show sharply: leave it out
            pieces.append(piece)
    if fill > len(pieces):
        skip = [pl["face_frame"]] if pl["face_frame"] is not None else []
        pieces += [("card", f) for f in other_moments(frames, skip, fill - len(pieces))]
    scene = next((frames[it["frame"]] for it in pl["items"] if it["kind"] == "scene"), None)
    face_frame = frames[pl["face_frame"]] if pl["face_frame"] is not None else None
    # a frame with as little face in it as possible, for backgrounds (no blurry "ghost" of the creator)
    quiet = min(frames, key=face_size)
    return {"accent": hex_rgb(pl["accent"]), "person": person, "face_crop": face_crop, "pieces": pieces,
            "scene": scene, "face_frame": face_frame, "quiet_frame": quiet, "any_frame": frames[0]}


def sharpness(img):
    g = np.asarray(img.convert("L").resize((320, int(320 * img.height / img.width))), dtype=np.float32)
    return float(np.var(np.diff(g, axis=0)) + np.var(np.diff(g, axis=1)))


def other_moments(frames, skip, want):
    """Up to `want` frames to fill the collage with: sharp, different from each other and from the
    `skip` frames, those without a big face first (the creator is already the main cut-out)."""
    look = {k: np.asarray(f.convert("L").resize((32, 18)), dtype=np.float32) for k, f in enumerate(frames)}
    sharp = {k: sharpness(f) for k, f in enumerate(frames)}
    floor = sorted(sharp.values())[len(sharp) // 4]  # the blurriest quarter is never used
    rank = sorted((k for k in sharp if k not in skip and sharp[k] >= floor),
                  key=lambda k: (face_size(frames[k]) > 0.12, -sharp[k]))
    chosen, seen = [], [look[k] for k in skip]
    for differ in (12, 7):  # clearly different moments first; then ones that differ a little less
        for k in rank:
            if len(chosen) >= want:
                return chosen
            if frames[k] in chosen or any(np.abs(look[k] - other).mean() < differ for other in seen):
                continue
            chosen.append(frames[k])
            seen.append(look[k])
    return chosen


def compose(frames, pl):
    """The thumbnail in the look saved in the plan (or THUMB_LOOK in .env, default burst). Each look is
    its own file in looks/; they share the cut-outs and drawing helpers here."""
    import importlib

    look = pl.get("look") or os.getenv("THUMB_LOOK", "burst").strip().lower()
    if look not in LOOKS:
        look = "burst"
    pl["look"] = look
    return importlib.import_module(f"pipeline.thumbnails.looks.{look}").render(frames, pl)


def save(img, path):
    for q in (92, 86, 80, 72):
        img.save(path, "JPEG", quality=q, optimize=True)
        if Path(path).stat().st_size <= MAX_BYTES:
            return
