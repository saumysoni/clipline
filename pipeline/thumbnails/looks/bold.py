"""
Bold look: a smooth gradient in the accent colour, an extra-large creator with a white outline, the
main thing the Short is about as a round badge, and big text. Minimal and graphic.
"""
from pipeline.thumbnails.layout import (H, W, circle_badge, draw_text_keyword, gradient_background, photo_card, place,
                                        place_person, prepare, with_shadow)

BADGES = [(250, 1250, 400), (880, 1420, 270)]  # (centre x, centre y, size): main badge, second badge
ALONE = [(540, 1000, 760), (800, 1500, 360)]


def render(frames, pl):
    parts = prepare(frames, pl, largest_slot=400)
    accent, person, face_crop = parts["accent"], parts["person"], parts["face_crop"]
    pieces = parts["pieces"][:2]
    if not person and face_crop is None and not pieces:
        raise RuntimeError("nothing to put on the thumbnail")
    canvas = gradient_background(accent)
    face = None
    if person:
        face = place_person(canvas, person[0], person[1], accent, face_x=0.55, head_top=0.25, height=0.72,
                            outline=16, glow=0, color=(255, 255, 255), shadow=True)
    elif face_crop is not None:
        place(canvas, with_shadow(photo_card(face_crop, 860, border=20), -2), W // 2, int(H * 0.66))
    spots = BADGES if person or face_crop is not None else ALONE
    for (kind, img), (cx, cy, size) in zip(pieces, spots):
        size = min(size, int(min(img.size) * 2.4))
        if face:  # keep badges below the chin
            cy = max(cy, int(face[3] + size * 0.6))
        if size >= 180:
            place(canvas, with_shadow(circle_badge(img, size), 0, blur=16, opacity=180), cx, cy)
    draw_text_keyword(canvas, pl["line1"], pl["line2"], accent, line2_fill=(255, 255, 255))
    return canvas.convert("RGB")
