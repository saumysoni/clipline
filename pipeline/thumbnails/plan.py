"""
Thumbnails, step 2: the AI looks at the frames and plans the collage (best face frame, up to 3
things worth showing with their position, text, accent colour). plan_without_ai() is the fallback.
Boxes are box_2d = [ymin, xmin, ymax, xmax] on a 0-1000 scale; clean_plan() checks everything.
"""
import hashlib
import io

from pipeline.ai import ai_json, image_part
from pipeline.thumbnails.frames import find_faces


ACCENTS = ["#FFD60A", "#00F5D4", "#FF4D6D", "#7CFF4F", "#4CC9F0", "#FF9F1C", "#C77DFF"]


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
        contents += [f"Frame {k}:", image_part(buf.getvalue())]
    raw = ai_json(contents, temperature=0.5)
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
