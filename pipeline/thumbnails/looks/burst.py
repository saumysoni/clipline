"""
Burst look: comic-style rays in the accent colour, the creator rising from the bottom with a neon
outline, the collage pieces around the head, text on a coloured block at the top.
"""
from pipeline.thumbnails.layout import (SLOTS_NO_FACE, SLOTS_WITH_FACE, MIN_PIECE, background, draw_text, photo_card,
                                        piece_size, place, place_person, prepare, scale_to, sticker, with_shadow, W, H)


def render(frames, pl):
    parts = prepare(frames, pl, largest_slot=940)
    accent, face_cut, face_crop, pieces = parts["accent"], parts["person"], parts["face_crop"], parts["pieces"]
    have_face = face_cut is not None or face_crop is not None
    if not have_face and not pieces:
        raise RuntimeError("nothing to put on the thumbnail")

    scene = next((frames[it["frame"]] for it in pl["items"] if it["kind"] == "scene"), None)
    if scene is not None:
        canvas = background(scene, accent)
    elif pl["face_frame"] is not None:
        canvas = background(frames[pl["face_frame"]], accent, blur=70)  # heavy blur: no ghost of the face
    else:
        canvas = background(frames[pl["items"][0]["frame"]], accent)

    slots = (SLOTS_WITH_FACE if have_face else SLOTS_NO_FACE).get(len(pieces), [])
    for (kind, img), (cx, cy, size, tilt) in zip(pieces, slots):
        size = piece_size(img, size) or MIN_PIECE
        if kind == "cut":
            art = sticker(scale_to(img, size, size), outline=16, color=(255, 255, 255))
        else:
            art = photo_card(img, size)
        place(canvas, with_shadow(art, tilt), cx, cy)

    if face_cut is not None:
        place_person(canvas, face_cut[0], face_cut[1], accent)
    elif face_crop is not None:  # no cut-out worked, but the face is big enough to show as a framed photo
        art = with_shadow(photo_card(face_crop, 820, border=24), -3)
        place(canvas, art, W // 2, int(H * 0.70))

    draw_text(canvas, pl["line1"], pl["line2"], accent)
    return canvas.convert("RGB")
