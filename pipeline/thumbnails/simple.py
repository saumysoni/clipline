"""
The simple thumbnail style: one frame from the Short with bold text.
"""
from pathlib import Path

from pipeline.constants import OUT_H, OUT_W
from pipeline.ffmpeg import ffmpeg_exe, run
from pipeline.fonts import find_font_file
from pipeline.reframe import crop_filter
from pipeline.text import without_emoji


def make_simple_thumbnail(video_path, meta, moment, cx, idx, job_dir):
    from PIL import Image, ImageDraw, ImageFont

    job_dir = Path(job_dir)
    raw = job_dir / f"frame_{idx}.jpg"
    t = moment["start"] + (moment["end"] - moment["start"]) * 0.3
    run([ffmpeg_exe(), "-y", "-ss", f"{t:.2f}", "-i", str(Path(video_path).resolve()),
         "-frames:v", "1", "-vf", crop_filter(meta, cx), "-q:v", "2", str(raw)])
    img = Image.open(raw).convert("RGB")

    # darken the lower part so text pops
    shade = Image.new("L", (1, OUT_H))
    for y in range(OUT_H):
        shade.putpixel((0, y), int(max(0, (y - OUT_H * 0.45) / (OUT_H * 0.55)) * 190))
    black = Image.new("RGB", img.size, (0, 0, 0))
    img = Image.composite(black, img, shade.resize(img.size))

    d = ImageDraw.Draw(img)
    font_path = find_font_file()

    def font(size):
        return ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default()

    def fit(text, max_size):
        size = max_size
        while size > 50:
            f = font(size)
            if d.textlength(text, font=f) <= OUT_W - 140:
                return f
            size -= 6
        return font(size)

    l1 = without_emoji(moment.get("thumb_line1") or "").upper()
    l2 = without_emoji(moment.get("thumb_line2") or moment.get("hook") or "").upper()
    y = OUT_H - 560
    if l1:
        f1 = fit(l1, 140)
        d.text((70, y), l1, font=f1, fill="white", stroke_width=8, stroke_fill="black")
        y += f1.size + 30
    if l2:
        f2 = fit(l2, 150)
        tw = d.textlength(l2, font=f2)
        d.rounded_rectangle((52, y - 10, 70 + tw + 22, y + f2.size + 26), radius=18, fill=(255, 214, 10))
        d.text((70, y), l2, font=f2, fill=(17, 17, 17))
    name = f"thumb_{idx}.jpg"
    img.save(job_dir / name, quality=92)
    raw.unlink(missing_ok=True)
    return name
