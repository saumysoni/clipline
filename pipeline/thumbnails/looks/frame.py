"""
Frame look (the default): the best moment of the Short, cropped to 9:16 around the creator's face (or
whatever the Short is about), colour-graded, with creator-style text kept off the face. Simple, honest,
like the thumbnails successful vlog channels make by hand.
"""
from pipeline.thumbnails.layout import add_text, grade, portrait


def render(frames, pl):
    img = frames[pl["frame"]]
    canvas = grade(portrait(img, pl.get("focus"))).convert("RGBA")
    add_text(canvas, img, pl)
    return canvas.convert("RGB")
