"""
Scene look: the real location as the background (colour-graded, softly blurred), the creator big with
a clean white outline and a soft shadow, the things the Short is about as stickers in front, and bold
text with the keyword in the accent colour. Closest to what travel and vlog creators make by hand.
"""
from pipeline.thumbnails.layout import (MIN_PIECE, H, W, draw_text_keyword, graded_background, photo_card,
                                        piece_size, place, place_person, prepare, scale_to, sticker, with_shadow)

# (centre x, centre y, size, tilt) for 1-2 pieces, in front of the creator's lower half
WITH_PERSON = {1: [(800, 1420, 520, 6)], 2: [(250, 1450, 450, -7), (830, 1380, 450, 6)]}
ALONE = {1: [(540, 1050, 900, -2)], 2: [(380, 900, 640, -5), (700, 1400, 640, 5)]}


def render(frames, pl):
    parts = prepare(frames, pl, largest_slot=900)
    accent, person, face_crop = parts["accent"], parts["person"], parts["face_crop"]
    pieces = parts["pieces"][:2]
    if not person and face_crop is None and not pieces:
        raise RuntimeError("nothing to put on the thumbnail")
    base = parts["scene"] if parts["scene"] is not None else parts["quiet_frame"]
    canvas = graded_background(base, accent, blur=8 if parts["scene"] is not None else 40)
    face = None
    if person:
        face = place_person(canvas, person[0], person[1], accent, head_top=0.27, height=0.66, outline=12, glow=0,
                            color=(255, 255, 255), shadow=True)
    elif face_crop is not None:
        place(canvas, with_shadow(photo_card(face_crop, 820, border=20), -2), W // 2, int(H * 0.66))
    slots = (WITH_PERSON if person or face_crop is not None else ALONE).get(len(pieces), [])
    for (kind, img), (cx, cy, size, tilt) in zip(pieces, slots):
        size = piece_size(img, size) or MIN_PIECE
        if face:  # keep pieces below the chin
            cy = max(cy, int(face[3] + size * 0.6))
        art = sticker(scale_to(img, size, size), outline=14, color=(255, 255, 255)) if kind == "cut" \
            else photo_card(img, size, border=14)
        place(canvas, with_shadow(art, tilt, blur=18, opacity=170), cx, cy)
    draw_text_keyword(canvas, pl["line1"], pl["line2"], accent)
    return canvas.convert("RGB")
