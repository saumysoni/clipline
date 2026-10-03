"""
Burst look (the default): comic-style rays in the accent colour, a full collage of cut-outs and shaped
photos (circles, rounded squares, arches, polaroids) filling the frame, and the creator biggest, rising
from the bottom with a neon outline: two pieces beside the head behind her, the rest at the edges in
front of her outline (never over the face). Creator-style text at the top.
"""
from pipeline.thumbnails.layout import (BEHIND, MIN_PIECE, SHAPES, SLOTS_AROUND_FACE, SLOTS_NO_FACE, H, W, background,
                                        draw_text, photo_card, piece_size, place, place_person, prepare, scale_to,
                                        shaped_card, sticker, with_shadow)


def render(frames, pl):
    have_face_frame = pl["face_frame"] is not None
    slots = SLOTS_AROUND_FACE if have_face_frame else SLOTS_NO_FACE
    parts = prepare(frames, pl, largest_slot=slots[0][2], fill=len(slots))
    accent, face_cut, face_crop, pieces = parts["accent"], parts["person"], parts["face_crop"], parts["pieces"]
    have_face = face_cut is not None or face_crop is not None
    if not have_face and not pieces:
        raise RuntimeError("nothing to put on the thumbnail")
    if not have_face and have_face_frame:  # the face didn't work out after all: use the no-face layout
        slots = SLOTS_NO_FACE

    if parts["scene"] is not None:
        canvas = background(parts["scene"], accent)
    else:  # heavy blur of a frame without a big face: no ghost of the creator behind the creator
        canvas = background(parts["quiet_frame"], accent, blur=60)

    shapes = iter(SHAPES * 3)

    def piece_art(kind, img, size):
        size = piece_size(img, size) or MIN_PIECE
        if kind == "cut":
            return sticker(scale_to(img, size, size), outline=14, color=(255, 255, 255))
        return shaped_card(img, size, next(shapes))

    placed = list(zip(pieces, slots))
    behind, front = (placed[:BEHIND], placed[BEHIND:]) if face_cut is not None else (placed, [])
    for (kind, img), (cx, cy, size, tilt) in behind:
        place(canvas, with_shadow(piece_art(kind, img, size), tilt), cx, cy)

    if face_cut is not None:
        # a little smaller than the other looks, so the collage around her shows
        face = place_person(canvas, face_cut[0], face_cut[1], accent, head_top=0.30, height=0.62, max_face=0.46)
        for (kind, img), (cx, cy, size, tilt) in front:  # at the edges, over the creator's outline
            art = piece_art(kind, img, size)
            l, t = cx - art.width / 2, cy - art.height / 2
            near = 0.08 * (face[2] - face[0])
            if l < face[2] + near and l + art.width > face[0] - near and t < face[3] + near and t + art.height > face[1] - near:
                continue  # never over the face
            place(canvas, with_shadow(art, tilt), cx, cy)
    elif face_crop is not None:  # no cut-out worked, but the face is big enough to show as a framed photo
        art = with_shadow(photo_card(face_crop, 760, border=24), -3)
        place(canvas, art, W // 2, int(H * 0.68))

    draw_text(canvas, pl["line1"], pl["line2"], accent)
    return canvas.convert("RGB")
