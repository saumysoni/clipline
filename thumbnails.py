"""
Thumbnails: a sticker-style cut-out of the creator with a bright outline, plus a collage
("vision board") of the other things the Short shows: cut-out objects and tilted photo cards.

  1. sample_frames()   ~10 frames spread across the clip
  2. plan()            the AI (Gemini or OpenAI) looks at the frames and picks the best face frame,
                       up to 3 things worth showing (with their position in the frame), the text and an accent
                       colour. Without the AI, plan_without_ai() uses face detection instead.
  3. cut_out()         rembg removes backgrounds (runs on the processor; no GPU needed)
  4. compose()         lays everything out on a 1080x1920 canvas

Everything here is portable (Pillow, OpenCV, rembg/onnxruntime), so it runs the same on a cloud
server as on a laptop. pipeline.make_thumbnail() falls back to the simple style if this fails.
"""
import hashlib
import io
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

import pipeline as P

W, H = P.OUT_W, P.OUT_H
N_FRAMES = 10
ACCENTS = ["#FFD60A", "#00F5D4", "#FF4D6D", "#7CFF4F", "#4CC9F0", "#FF9F1C", "#C77DFF"]
MAX_BYTES = 2 * 1024 * 1024  # YouTube's thumbnail size limit

_REMBG = {}


# --------------------------------------------------------------------------- 1. frames
def sample_frames(video_path, start, end, work, n=N_FRAMES):
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    span = max(0.5, end - start - 1.0)
    frames = []
    for k in range(n):
        t = start + 0.5 + span * (k + 0.5) / n
        out = work / f"frame_{k}.jpg"
        P.run([P.ffmpeg_exe(), "-y", "-ss", f"{t:.2f}", "-i", str(Path(video_path).resolve()),
               "-frames:v", "1", "-vf", "scale='min(1280,iw)':-2", "-q:v", "2", str(out)])
        if out.exists():
            frames.append(Image.open(out).convert("RGB"))
    if not frames:
        raise RuntimeError("couldn't read frames")
    return frames


def find_faces(img):
    """Largest face (x, y, w, h) in pixels plus a quality score, or (None, 0)."""
    try:
        import cv2
        if not hasattr(cv2, "CascadeClassifier"):
            return None, 0.0
        gray = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(max(40, img.width // 20),) * 2)
        if not len(faces):
            return None, 0.0
        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
        sharp = cv2.Laplacian(gray[y:y + h, x:x + w], cv2.CV_64F).var()
        return (int(x), int(y), int(w), int(h)), (w * h) / (img.width * img.height) * (sharp ** 0.5)
    except Exception:  # noqa: BLE001
        return None, 0.0


# --------------------------------------------------------------------------- 2. plan
PLAN_PROMPT = """You are designing a scroll-stopping YouTube Shorts thumbnail, collage style.
Below are {n} frames (numbered 0 to {last}) from one Short.

Short title: {title}
On-screen hook: {hook}
What is said in the Short: {said}
{vlog}
Return ONLY a JSON object:
{{
  "face_frame": number of the frame where the creator's face is clearest, biggest and most expressive
                (a strong reaction is best), ideally with nobody else right next to them (they get cut out
                of the frame, so overlapping people spoil it), or null if no frame shows a clear face,
  "items": up to 3 distinct, visually interesting things this Short is about (food, animal, vehicle,
           landmark, product, view...). Never the creator. Each:
           {{"frame": number, "label": "2-4 words",
             "box_2d": [ymin, xmin, ymax, xmax] of the thing in that frame, scaled 0-1000,
             "kind": "object" if it's one thing that can be cut out cleanly, "scene" for views, streets,
                     rooms and landscapes}},
  "line1": thumbnail text line 1, max 3 words,
  "line2": thumbnail text line 2, max 3 words, the punchy part,
  "accent": the colour that best fits the mood, one of {accents}
}}
Prefer fewer, clearer items over many weak ones. Use [] if nothing besides the creator stands out.
"""


def plan(frames, moment, words=None, context=None):
    said = ""
    if words:
        said = " ".join(w["w"] for w in words if moment["start"] - 0.1 <= w["s"] <= moment["end"])[:1500]
    vlog = f"Vlog title: {context['title']}\n" if context and context.get("title") else ""
    text = PLAN_PROMPT.format(n=len(frames), last=len(frames) - 1, title=moment.get("title", ""),
                              hook=moment.get("hook", ""), said=said or "(not available)", vlog=vlog,
                              accents=", ".join(ACCENTS))
    contents = [text]
    for k, f in enumerate(frames):
        small = f.copy()
        small.thumbnail((512, 512))
        buf = io.BytesIO()
        small.save(buf, "JPEG", quality=80)
        contents += [f"Frame {k}:", P.image_part(buf.getvalue())]
    raw = P.ai_json(contents, temperature=0.5)
    return clean_plan(raw, frames, moment)


def clean_plan(raw, frames, moment):
    """Validate whatever came back; anything odd is dropped rather than trusted."""
    raw = raw if isinstance(raw, dict) else {}
    n = len(frames)

    def frame_no(v):
        try:
            v = int(v)
            return v if 0 <= v < n else None
        except (TypeError, ValueError):
            return None

    items = []
    for it in (raw.get("items") or [])[:3]:
        if not isinstance(it, dict):
            continue
        k, box = frame_no(it.get("frame")), it.get("box_2d")
        try:
            y0, x0, y1, x1 = [min(1000.0, max(0.0, float(v))) for v in box]
        except (TypeError, ValueError):
            continue
        if k is None or y1 - y0 < 60 or x1 - x0 < 60:
            continue
        items.append({"frame": k, "label": str(it.get("label", ""))[:40], "box": (y0, x0, y1, x1),
                      "kind": "object" if it.get("kind") == "object" else "scene"})
    accent = raw.get("accent") if raw.get("accent") in ACCENTS else pick_accent(moment)
    return {"face_frame": frame_no(raw.get("face_frame")), "items": items, "accent": accent,
            "line1": str(raw.get("line1") or moment.get("thumb_line1") or "")[:30],
            "line2": str(raw.get("line2") or moment.get("thumb_line2") or moment.get("hook") or "")[:30]}


def plan_without_ai(frames, moment):
    scores = [find_faces(f)[1] for f in frames]
    best = max(range(len(frames)), key=lambda k: scores[k])
    return {"face_frame": best if scores[best] > 0 else None, "items": [], "accent": pick_accent(moment),
            "line1": moment.get("thumb_line1", ""), "line2": moment.get("thumb_line2") or moment.get("hook", "")}


def pick_accent(moment):
    h = int(hashlib.md5(str(moment.get("title", "")).encode()).hexdigest(), 16)
    return ACCENTS[h % len(ACCENTS)]


# --------------------------------------------------------------------------- 3. cut-outs
def rembg_session():
    """Background remover, loaded once per process. None if rembg isn't installed."""
    name = os.getenv("THUMB_CUTOUT_MODEL", "isnet-general-use")
    if name not in _REMBG:
        try:
            from rembg import new_session
            _REMBG[name] = new_session(name)
        except Exception as e:  # noqa: BLE001
            print(f"Cut-outs unavailable ({e}); using photo cards instead.")
            _REMBG[name] = None
    return _REMBG[name]


def cut_out(img, keep_point=None):
    """RGBA cut-out of the main subject, cleaned up, or None if it didn't work well."""
    sess = rembg_session()
    if sess is None:
        return None
    from rembg import remove
    from scipy import ndimage

    rgba = remove(img, session=sess)
    a = np.asarray(rgba.getchannel("A"), dtype=np.float32) / 255.0
    solid = a > 0.5
    # Shrink the mask a little before splitting it into separate blobs, so things that only touch the
    # subject through a thin bridge (someone else's arm, a seat edge) come apart; then grow it back.
    r = max(2, int(min(solid.shape) * 0.012))
    core = ndimage.binary_erosion(solid, iterations=r)
    labels, count = ndimage.label(core if core.any() else solid)
    if count == 0:
        return None
    if keep_point and 0 <= keep_point[1] < labels.shape[0] and 0 <= keep_point[0] < labels.shape[1] \
            and labels[keep_point[1], keep_point[0]]:
        keep = labels[keep_point[1], keep_point[0]]
    else:
        keep = 1 + int(np.argmax(ndimage.sum(labels > 0, labels, range(1, count + 1))))
    mask = ndimage.binary_dilation(labels == keep, iterations=r + 1) & solid
    mask = ndimage.binary_fill_holes(mask)
    coverage = mask.mean()
    if not 0.04 <= coverage <= 0.92:  # nothing found, or nothing removed
        return None
    alpha = Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2))
    out = rgba.convert("RGB").convert("RGBA")
    out.putalpha(alpha)
    return out.crop(out.getbbox())


def crop_box(img, box, pad=0.08):
    y0, x0, y1, x1 = box
    w, h = img.size
    bw, bh = (x1 - x0) / 1000 * w, (y1 - y0) / 1000 * h
    l = max(0, int(x0 / 1000 * w - bw * pad))
    t = max(0, int(y0 / 1000 * h - bh * pad))
    r = min(w, int(x1 / 1000 * w + bw * pad))
    b = min(h, int(y1 / 1000 * h + bh * pad))
    return img.crop((l, t, r, b))


def face_cutout(img):
    """The creator from the chest up, cut out. Crops around the face first so other people
    and the background confuse the cut-out less."""
    face, _ = find_faces(img)
    if face:
        x, y, w, h = face
        # head and shoulders only: about 1.2 face-widths either side, so people sitting next to
        # the creator (a driver, a friend) don't get pulled into the cut-out
        box = (max(0, int(x - 1.2 * w)), max(0, int(y - 0.9 * h)),
               min(img.width, int(x + 2.2 * w)), min(img.height, int(y + 4.2 * h)))
        crop = img.crop(box)
        point = (x + w // 2 - box[0], y + h // 2 - box[1])
    else:
        crop, point = img, None
    cut = cut_out(crop, keep_point=point)
    return cut, crop


# --------------------------------------------------------------------------- 4. compose
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
    path = P.find_font_file()
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
    l1, l2 = (line1 or "").upper().strip(), (line2 or "").upper().strip()
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


def make_collage_thumbnail(video_path, moment, idx, job_dir, words=None, context=None):
    job_dir = Path(job_dir)
    work = job_dir / f"thumbwork_{idx}"
    frames = sample_frames(video_path, moment["start"], moment["end"], work)
    try:
        pl = plan(frames, moment, words, context)
    except Exception as e:  # noqa: BLE001  (no key, Gemini busy, odd answer...)
        print(f"Thumbnail planning without AI ({e}).")
        pl = plan_without_ai(frames, moment)
    img = compose(frames, pl)
    name = f"thumb_{idx}.jpg"
    save(img, job_dir / name)
    (work / "plan.json").write_text(__import__("json").dumps(pl, indent=1), encoding="utf-8")
    return name
