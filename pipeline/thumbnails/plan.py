"""
Thumbnails, step 2: the AI looks at the frames and picks the best moment for the thumbnail, where its
subject is (to crop around), the text and an accent colour. plan_without_ai() is the fallback.
Boxes are box_2d = [ymin, xmin, ymax, xmax] on a 0-1000 scale; clean_plan() checks everything.

Thumbnails use Gemini by default whatever AI_PROVIDER says (Gemini is trained to mark where things are
in a picture). THUMB_AI_PROVIDER changes the first choice; a provider that fails (no key, busy, limit
used up) is skipped for REST seconds, then the other provider is tried, then no AI.
"""
import hashlib
import io
import json
import os
import re
import threading
import time
from pathlib import Path

from pipeline.ai import ai_json, has_key, image_part
from pipeline.thumbnails.frames import find_faces


ACCENTS = ["#FFD60A", "#00F5D4", "#FF4D6D", "#7CFF4F", "#4CC9F0", "#FF9F1C", "#C77DFF"]


AI_TIMEOUT = 60    # seconds one planning request may take (it normally takes 5-20)
AI_DEADLINE = 120  # seconds the whole planning may take, every model and provider included
REST = 180         # seconds a provider that just failed (busy, limit) is skipped by the other thumbnails


PLAN_PROMPT = """You are choosing the thumbnail for a YouTube Short: one frame of the Short plus a short text.
Below are {n} frames (numbered 0 to {last}).

Short title: {title}
On-screen hook: {hook}
What is said in the Short: {said}
{vlog}
Pick the single frame that would make the most people stop scrolling and tap: sharp (no motion blur),
well lit, and either the creator's face big and expressive (a strong reaction is best; eyes open, not
mid-blink) or, if it says more, the thing the Short is about (a dish, a view, a place) big and clear.

Return ONLY a JSON object:
{{
  "frame": the number of that frame,
  "focus": [ymin, xmin, ymax, xmax] tightly around what the thumbnail must keep in view (usually the
           creator's face) in that frame, scaled 0-1000,
  "line1": a small line above the headline, 1-3 words, or "",
  "line2": the headline, 1-3 words, the punchy part,
  "accent": the colour that best fits the mood, one of {accents}
}}
Text rules: line1 and line2 read as one phrase and never repeat a word (not "RICE OLDER? / OLDER THAN
ME" but "RICE / OLDER THAN ME"); no emoji; nothing that isn't true to the Short.
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
    return clean_plan(ask_ai(contents), frames, moment)


_RESTING, _REST_LOCK = {}, threading.Lock()


def thumb_providers():
    """Which AIs to ask, in order: THUMB_AI_PROVIDER (default gemini), then the other one, skipping any
    without an API key in .env and any that failed in the last REST seconds."""
    first = (os.getenv("THUMB_AI_PROVIDER") or "gemini").strip().lower()
    order = [first] + [p for p in ("gemini", "openai") if p != first]
    with _REST_LOCK:
        ready = [p for p in order if has_key(p) and _RESTING.get(p, 0) <= time.time()]
    return ready or [p for p in order if has_key(p)]  # all resting: try anyway rather than not at all


def ask_ai(contents):
    """The plan from the first AI that answers. Raises if none can, and the caller then plans without AI."""
    providers, last = thumb_providers(), None
    if not providers:
        raise RuntimeError("no AI key in .env")
    for provider in providers:
        try:
            # a thumbnail can always be made without the AI, so don't wait long for it
            return ai_json(contents, temperature=0.5, provider=provider, timeout=AI_TIMEOUT, busy_waits=[])
        except Exception as e:  # noqa: BLE001  (busy, limit used up, bad key...: try the next one)
            print(f"Thumbnail planning with {provider} didn't work ({e}); skipping it for {REST}s.")
            with _REST_LOCK:  # the other thumbnails (made at the same time) go straight to the next one
                _RESTING[provider] = time.time() + REST
            last = e
    raise last


def tidy_lines(line1, line2):
    """The two text lines without repeats: a word already in the headline is dropped from the small line
    ("Rice Older?" + "Older Than Me" -> "Rice" + "Older Than Me"). Also trims spaces and lengths."""
    l1, l2 = " ".join(str(line1 or "").split())[:30], " ".join(str(line2 or "").split())[:30]
    key = lambda w: re.sub(r"[^\w]", "", w.lower())  # noqa: E731
    head = {key(w) for w in l2.split() if key(w)}
    l1 = " ".join(w for w in l1.split() if key(w) not in head).strip(" -,:")
    if l1 and not re.search(r"\w", l1):
        l1 = ""
    return l1, l2


def clean_plan(raw, frames, moment):
    """Validate whatever came back; anything odd is replaced by the face finder's choice."""
    raw = raw if isinstance(raw, dict) else {}
    try:
        k = int(raw.get("frame"))
        k = k if 0 <= k < len(frames) else None
    except (TypeError, ValueError):
        k = None
    try:
        y0, x0, y1, x1 = [min(1000.0, max(0.0, float(v))) for v in raw.get("focus")]
        focus = (y0, x0, y1, x1) if y1 - y0 >= 20 and x1 - x0 >= 20 else None
    except (TypeError, ValueError):
        focus = None
    if k is None:
        fallback = plan_without_ai(frames, moment)
        k, focus = fallback["frame"], fallback["focus"]
    accent = raw.get("accent") if raw.get("accent") in ACCENTS else pick_accent(moment)
    l1, l2 = tidy_lines(raw.get("line1") if raw.get("line1") is not None else moment.get("thumb_line1", ""),
                        raw.get("line2") or moment.get("thumb_line2") or moment.get("hook") or "")
    return {"frame": k, "focus": focus, "line1": l1, "line2": l2, "accent": accent, "ai": True}


def face_box(img):
    """The face finder's largest face as box_2d (0-1000), or None."""
    face, _ = find_faces(img)
    if not face:
        return None
    x, y, w, h = face
    return (y / img.height * 1000, x / img.width * 1000, (y + h) / img.height * 1000, (x + w) / img.width * 1000)


def sharpness(img):
    import numpy as np
    g = np.asarray(img.convert("L").resize((320, max(1, int(320 * img.height / img.width)))), dtype=np.float32)
    return float(np.var(np.diff(g, axis=0)) + np.var(np.diff(g, axis=1)))


def plan_without_ai(frames, moment):
    """The frame with the biggest, sharpest face (else the sharpest frame), cropped around that face."""
    scores = [find_faces(f)[1] for f in frames]
    k = max(range(len(frames)), key=lambda i: scores[i]) if max(scores) > 0 else \
        max(range(len(frames)), key=lambda i: sharpness(frames[i]))
    l1, l2 = tidy_lines(moment.get("thumb_line1", ""), moment.get("thumb_line2") or moment.get("hook", ""))
    return {"frame": k, "focus": face_box(frames[k]), "line1": l1, "line2": l2, "accent": pick_accent(moment),
            "ai": False}


def upgrade_plan(pl):
    """Plans saved before the frame look (collage era: face_frame / face_box / items) in today's shape."""
    if "frame" not in pl:
        pl["frame"] = pl.get("face_frame")
        if pl["frame"] is None:
            pl["frame"] = next((it.get("frame") for it in pl.get("items") or []), 0)
        pl["focus"] = pl.get("face_box")
    pl.setdefault("focus", None)
    pl["line1"], pl["line2"] = tidy_lines(pl.get("line1", ""), pl.get("line2", ""))
    for old in ("face_frame", "face_box", "person_box", "items"):
        pl.pop(old, None)
    return pl


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
