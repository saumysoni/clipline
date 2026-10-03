"""
Thumbnails, step 2: the AI looks at the frames and plans the collage (best face frame, up to 3
things worth showing with their position, text, accent colour). plan_without_ai() is the fallback.
Boxes are box_2d = [ymin, xmin, ymax, xmax] on a 0-1000 scale; clean_plan() checks everything.

Thumbnails use Gemini by default whatever AI_PROVIDER says, because Gemini is trained to mark where
things are in a picture (box_2d) and the cut-outs depend on that. THUMB_AI_PROVIDER changes the first
choice; if it can't answer (no key, busy, limit used up), the other provider is tried, then no AI.
"""
import hashlib
import io
import json
import os
from pathlib import Path

from pipeline.ai import ai_json, has_key, image_part
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
  "face_box": [ymin, xmin, ymax, xmax] tightly around the creator's face in that frame, scaled 0-1000
              (the creator, not anyone else in the frame), or null,
  "items": up to 3 distinct things this Short is about (food, animal, vehicle, landmark, product,
           view...), never the creator. They must match the title, hook or what is said: if the title
           names something (a dish, a place, a price), show THAT thing, first. Never pick random
           background objects. Only include a thing if it is big, sharp and clearly recognisable in
           the frame (roughly a fifth of the frame's width or height, or more); skip tiny, distant or
           blurry things even if they're relevant. Each:
           {{"frame": number, "label": "2-4 words",
             "box_2d": [ymin, xmin, ymax, xmax] tightly around the thing in that frame, scaled 0-1000,
             "kind": "object" if it's one thing that can be cut out cleanly, "scene" for views, streets,
                     rooms and landscapes}},
  "line1": thumbnail text line 1, max 3 words,
  "line2": thumbnail text line 2, max 3 words, the punchy part,
  "accent": the colour that best fits the mood, one of {accents}
}}
Prefer fewer, clearer items over many weak ones. Use [] if nothing besides the creator stands out:
an empty collage looks better than a wrong or blurry one.
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
    raw = ask_ai(contents)
    return clean_plan(raw, frames, moment)


def thumb_providers():
    """Which AIs to ask, in order: THUMB_AI_PROVIDER (default gemini), then the other one, skipping any
    without an API key in .env."""
    first = (os.getenv("THUMB_AI_PROVIDER") or "gemini").strip().lower()
    order = [first] + [p for p in ("gemini", "openai") if p != first]
    return [p for p in order if has_key(p)]


def ask_ai(contents):
    """The plan from the first AI that answers. Raises if none can, and the caller then plans without AI."""
    providers, last = thumb_providers(), None
    if not providers:
        raise RuntimeError("no AI key in .env")
    for provider in providers:
        try:
            return ai_json(contents, temperature=0.5, provider=provider)
        except Exception as e:  # noqa: BLE001  (busy, limit used up, bad key...: try the next one)
            print(f"Thumbnail planning with {provider} didn't work ({e}).")
            last = e
    raise last


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
    face_frame, face_box = frame_no(raw.get("face_frame")), None
    try:
        y0, x0, y1, x1 = [min(1000.0, max(0.0, float(v))) for v in raw.get("face_box")]
        if face_frame is not None and y1 - y0 >= 20 and x1 - x0 >= 20:
            face_box = (y0, x0, y1, x1)
    except (TypeError, ValueError):
        pass
    return {"face_frame": face_frame, "face_box": face_box, "items": items, "accent": accent,
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


def fresh_accent(job_dir, work_name, wanted):
    """`wanted` unless another Short of this vlog already uses it; then the next colour nobody uses,
    so a batch of Shorts doesn't all come out yellow. Repeats only once all colours are taken."""
    used = []
    for other in sorted(Path(job_dir).glob("thumbwork_*/plan.json")):
        if other.parent.name == work_name:
            continue
        try:
            used.append(json.loads(other.read_text(encoding="utf-8")).get("accent"))
        except (OSError, ValueError):
            pass
    if wanted not in used:
        return wanted
    start = ACCENTS.index(wanted) if wanted in ACCENTS else 0
    free = [ACCENTS[(start + k) % len(ACCENTS)] for k in range(1, len(ACCENTS))
            if ACCENTS[(start + k) % len(ACCENTS)] not in used]
    return free[0] if free else wanted
