"""
A whole vlog's YouTube thumbnail (1280x720): the AI picks the best frame from across the vlog and where the
creator's face is; the text goes on the other side, big, in the same creator style as the Shorts' thumbnails
(a small serif line over a huge condensed headline). Two looks, like the Shorts: frame and duotone.
The frames and plan are kept in vthumbwork/, so switching the look or the text redraws it without the AI.
"""
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from pipeline.thumbnails.frames import sample_frames
from pipeline.thumbnails.layout import LOOKS, fit_font, grade, hex_rgb, save
from pipeline.thumbnails.plan import ACCENTS, ask_ai
from pipeline.ai import image_part
from pipeline.text import without_emoji

W, H = 1280, 720
N_FRAMES = 16
WORK = "vthumbwork"

PROMPT = """You are choosing the thumbnail for a full YouTube vlog (landscape, 16:9): one frame plus a short text.
Below are {n} frames from across the vlog (numbered 0 to {last}).
Vlog title: {title}
Suggested text: "{line1}" / "{line2}"

Pick the single frame that would make the most people click: sharp, well lit, and either the creator's face
big and expressive or, if it says more, the place/thing the vlog is about, big and clear.

Return ONLY a JSON object:
{{
  "frame": the number of that frame,
  "focus": [ymin, xmin, ymax, xmax] tightly around what must stay visible (usually the face), scaled 0-1000,
  "line1": a small line above the headline, 1-3 words, or "",
  "line2": the headline, 1-3 punchy words,
  "accent": one of {accents}
}}
line1 and line2 read as one phrase, never repeat a word, no emoji, nothing untrue to the vlog.
"""


def _cover(img, focus):
    """A 16:9 crop of img (any shape) filling W x H, keeping `focus` in view, and the focus centre (0-1 across)."""
    fx, fy = 0.5, 0.45
    if focus:
        fy, fx = (focus[0] + focus[2]) / 2000, (focus[1] + focus[3]) / 2000
    iw, ih = img.size
    if iw / ih > W / H:
        cw, ch = round(ih * W / H), ih
    else:
        cw, ch = iw, round(iw * H / W)
    left = min(max(0, round(fx * iw - cw / 2)), iw - cw)
    top = min(max(0, round(fy * ih - ch / 2)), ih - ch)
    out = img.crop((left, top, left + cw, top + ch)).resize((W, H), Image.LANCZOS)
    return out, (fx * iw - left) / cw


def _text(canvas, line1, line2, text_left, accent):
    """Creator-style text on one half (the side away from the face), with a soft shade behind it."""
    shade = Image.linear_gradient("L").rotate(90 if text_left else -90, expand=True).resize((W, H))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    layer.putalpha(shade.point(lambda v: int(max(0, v - 90) / 165 * 200)))
    canvas.alpha_composite(layer)
    d = ImageDraw.Draw(canvas)
    l1, l2 = without_emoji(line1).strip().upper(), without_emoji(line2).strip().upper()
    box_w = int(W * 0.5)
    x0 = 56 if text_left else W - box_w - 56
    lines = []
    if l1:
        f1 = fit_font(d, l1, 64, box_w, "kicker", 32)
        lines.append((l1, f1, 2, (255, 255, 255)))
    if l2:
        words = l2.split()
        parts = [l2] if len(words) < 3 else [" ".join(words[:len(words) // 2]), " ".join(words[len(words) // 2:])]
        f2 = min((fit_font(d, t, 210, box_w, "head", 80) for t in parts), key=lambda f: f.size)
        lines += [(t, f2, 4, hex_rgb(accent) if k == len(parts) - 1 else (255, 255, 255)) for k, t in enumerate(parts)]
    heights = [int(f.size * 1.08) for _, f, _, _ in lines]
    y = (H - sum(heights)) // 2
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    pos = []
    for (t, f, stroke, color), h in zip(lines, heights):
        x = x0 if text_left else x0 + box_w - d.textlength(t, font=f)
        pos.append((x, y, t, f, stroke, color))
        sd.text((x + 4, y + 8), t, font=f, fill=(0, 0, 0, 220), stroke_width=stroke + 8, stroke_fill=(0, 0, 0, 220))
        y += h
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(12)))
    d = ImageDraw.Draw(canvas)
    for x, y, t, f, stroke, color in pos:
        d.text((x, y), t, font=f, fill=color, stroke_width=stroke, stroke_fill=(15, 15, 15))


def render(frames, pl):
    img = frames[min(pl["frame"], len(frames) - 1)]
    pic, face_x = _cover(img, pl.get("focus"))
    if pl.get("look") == "duotone":
        g = np.asarray(ImageEnhance.Contrast(pic.convert("L")).enhance(1.45), dtype=np.float32)[..., None] / 255.0
        light, dark = np.array(hex_rgb(pl["accent"]), dtype=np.float32), np.array((14, 10, 34), dtype=np.float32)
        canvas = Image.fromarray((dark * (1 - g) + light * g).astype(np.uint8)).convert("RGBA")
        accent = "#FFFFFF"
    else:
        canvas = grade(pic).convert("RGBA")
        accent = pl["accent"]
    _text(canvas, pl.get("line1", ""), pl.get("line2", ""), text_left=face_x >= 0.5, accent=accent)
    return canvas.convert("RGB")


def _plan(frames, title, line1, line2):
    text = PROMPT.format(n=len(frames), last=len(frames) - 1, title=title or "(not given)", line1=line1, line2=line2,
                         accents=", ".join(ACCENTS))
    contents = [text]
    for k, f in enumerate(frames):
        small = f.copy()
        small.thumbnail((512, 512))
        buf = io.BytesIO()
        small.save(buf, "JPEG", quality=80)
        contents += [f"Frame {k}:", image_part(buf.getvalue())]
    raw = ask_ai(contents)
    raw = raw if isinstance(raw, dict) else {}
    frame = raw.get("frame")
    frame = frame if isinstance(frame, int) and 0 <= frame < len(frames) else len(frames) // 3
    focus = raw.get("focus")
    focus = focus if isinstance(focus, list) and len(focus) == 4 and all(isinstance(v, (int, float)) for v in focus) else None
    accent = raw.get("accent") if raw.get("accent") in ACCENTS else ACCENTS[0]
    return {"frame": frame, "focus": focus, "line1": str(raw.get("line1") or line1)[:30],
            "line2": str(raw.get("line2") or line2 or title or "")[:30], "accent": accent}


def make_vlog_thumbnail(video_path, duration, job_dir, title="", line1="", line2="", look=None):
    """Design the thumbnail; returns its file name (vthumb_1.jpg). Falls back to a plain pick without the AI."""
    job_dir = Path(job_dir)
    work = job_dir / WORK
    d = float(duration or 0)
    frames = sample_frames(video_path, d * 0.05, max(d * 0.95, 2.0), work, n=N_FRAMES)
    try:
        pl = _plan(frames, title, line1, line2)
    except Exception as e:  # noqa: BLE001  (no key, AI busy...: still a thumbnail)
        print("Vlog thumbnail planned without AI:", repr(e)[:200])
        pl = {"frame": len(frames) // 3, "focus": None, "line1": line1, "line2": line2 or title[:24], "accent": ACCENTS[0]}
    pl["look"] = look if look in LOOKS else LOOKS[0]
    pl["n"] = 1
    (work / "plan.json").write_text(json.dumps(pl, indent=1), encoding="utf-8")
    name = "vthumb_1.jpg"
    save(render(frames, pl), job_dir / name)
    return name


def redraw_vlog_thumbnail(job_dir, **changes):
    """Redraw with another look or text (no AI). Returns the new file name (a new number, so browsers reload it)."""
    job_dir = Path(job_dir)
    work = job_dir / WORK
    pl = json.loads((work / "plan.json").read_text(encoding="utf-8"))
    paths = sorted(work.glob("frame_*.jpg"), key=lambda f: int(f.stem.split("_")[1]))
    frames = [Image.open(f).convert("RGB") for f in paths]
    pl.update({k: v for k, v in changes.items() if v is not None})
    old = job_dir / f"vthumb_{pl.get('n', 1)}.jpg"
    pl["n"] = pl.get("n", 1) + 1
    name = f"vthumb_{pl['n']}.jpg"
    save(render(frames, pl), job_dir / name)
    (work / "plan.json").write_text(json.dumps(pl, indent=1), encoding="utf-8")
    old.unlink(missing_ok=True)
    return name
