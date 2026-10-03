"""
The creator's own moment (Add a Short / must-have moments): their From/To times are used as given,
snapped to whole words; the AI only writes the title, hook and thumbnail text.
"""
import re

from pipeline.ai import ai_json
from pipeline.hooks import HOOK_RULE, hook_fields
from pipeline.text import fmt_mmss, said_between
from pipeline.vlog_context import vlog_context_block


MANUAL_MIN, MANUAL_MAX = 5, 180  # a moment the creator times themselves (YouTube allows Shorts up to 3 minutes)


TEXT_PROMPT = """You are an expert short-form video editor for a YouTube creator. The creator chose this moment
of their vlog ({start} to {end}) for a YouTube Short. Write the text for it.
{note}
{hook_rule}
Return ONLY a JSON object with:
  "hooks": three on-screen hook options for the first seconds, each max 6 words:
           {{"curiosity": makes them need to know what happens, "bold": a strong claim or reaction,
             "story": sets up the story}},
  "hook_pick": which of the three is strongest: "curiosity", "bold" or "story",
  "title": YouTube title, max 60 characters, no hashtags,
  "thumb_line1": thumbnail text line 1, max 3 words,
  "thumb_line2": thumbnail text line 2, max 3 words (the punchy part),
  "why": one short sentence on why this moment works,
  "hashtags": array of 3 hashtags without the # sign

{context}WHAT IS SAID IN THIS MOMENT
{said}
"""


def snap_moment(transcript, start, end):
    """Check a moment's times and nudge them so no word is cut in half. Returns (start, end).
    Speech isn't required: the creator may want a scene without talking."""
    dur = transcript["duration"]
    if start >= dur:
        raise RuntimeError(f"{fmt_mmss(start)} is past the end of the video ({fmt_mmss(dur)}). Check the times.")
    start, end = max(0.0, start), min(end, dur)
    if end - start < MANUAL_MIN:
        raise RuntimeError(f"The moment from {fmt_mmss(start)} to {fmt_mmss(end)} is too short. "
                           f"Make it at least {MANUAL_MIN} seconds.")
    if end - start > MANUAL_MAX:
        raise RuntimeError(f"The moment from {fmt_mmss(start)} to {fmt_mmss(end)} is longer than 3 minutes, "
                           "the most YouTube allows for a Short. Shorten it.")
    words = transcript["words"]
    cut = next((w for w in words if w["s"] < start < w["e"]), None)
    if cut:
        start = cut["s"]
    cut = next((w for w in words if w["s"] < end < w["e"]), None)
    if cut:
        end = min(dur, cut["e"] + 0.2)
    return round(max(0.0, start - 0.1), 2), round(end, 2)


def moment_text(raw, fallback=None, said="", start=0.0):
    """Title, hook, thumbnail lines, why and hashtags from an AI answer, filling gaps from `fallback`
    (e.g. the Short being adjusted) or the words said, so a moment always has usable text."""
    raw = raw if isinstance(raw, dict) else {}
    fb = fallback or {}
    pick = lambda k: raw.get(k) or fb.get(k) or ""  # noqa: E731
    first = " ".join(said.split()[:8])
    return {
        **hook_fields(raw, said, fb),
        "title": str(pick("title") or first or f"Short from {fmt_mmss(start)}")[:90],
        "thumb_line1": str(pick("thumb_line1"))[:30],
        "thumb_line2": str(pick("thumb_line2"))[:30],
        "why": str(raw.get("why") or fb.get("why") or "You picked this moment."),
        "hashtags": [re.sub(r"[^\w]", "", str(h)) for h in (raw.get("hashtags") or fb.get("hashtags") or [])
                     if str(h).strip()][:5],
    }


def manual_moment(transcript, start, end, note="", progress=lambda pct, msg: None, context=None):
    """A moment the creator timed themselves. The AI only writes its text; if that fails, simple
    text is used, so a creator's own pick never fails because of the AI."""
    start, end = snap_moment(transcript, start, end)
    said = said_between(transcript, start, end)
    progress(30, "Writing the title and hook")
    raw = {}
    try:
        raw = ai_json(TEXT_PROMPT.format(
            hook_rule=HOOK_RULE, start=fmt_mmss(start), end=fmt_mmss(end), said=said[:4000] or "(no speech in this moment)",
            note=f"What the creator says about it: {note.strip()[:500]}\n" if note.strip() else "",
            context=vlog_context_block(context)), progress, temperature=0.5)
    except Exception as e:  # noqa: BLE001
        print(f"Couldn't write text for the creator's moment ({e}); using simple text.")
    return {"start": start, "end": end, "manual": True, **moment_text(raw, None, said, start)}
