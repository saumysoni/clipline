"""
Duotone look: the same moment as the frame look, in two colours (a deep shade for the shadows, the
Short's accent colour for the lights), poster style. Every Short of a vlog gets its own accent.
"""
import numpy as np
from PIL import Image, ImageEnhance

from pipeline.thumbnails.layout import add_text, hex_rgb, portrait


DARK = (14, 10, 34)


def render(frames, pl):
    img = frames[pl["frame"]]
    gray = ImageEnhance.Contrast(portrait(img, pl.get("focus")).convert("L")).enhance(1.45)
    g = np.asarray(gray, dtype=np.float32)[..., None] / 255.0
    light, dark = np.array(hex_rgb(pl["accent"]), dtype=np.float32), np.array(DARK, dtype=np.float32)
    canvas = Image.fromarray((dark * (1 - g) + light * g).astype(np.uint8)).convert("RGBA")
    add_text(canvas, img, pl, shade_strength=170)
    return canvas.convert("RGB")
