"""
Finding the best moments: the AI reads the whole transcript and picks stand-alone moments,
then clean_moments() snaps them to real word boundaries, enforces lengths and drops overlaps.
"""
import re

from pipeline.ai import ai_json
from pipeline.constants import MAX_LEN, MIN_LEN
from pipeline.hooks import HOOK_RULE, hook_fields
from pipeline.text import fmt_mmss, said_between
from pipeline.vlog_context import vlog_context_block


PICK_PROMPT = """You are an expert short-form video editor for a YouTube creator.
Below is the timestamped transcript of one long vlog ({duration}). Choose the {n} best moments
to turn into stand-alone YouTube Shorts.

A great moment:
- makes sense with no context from the rest of the vlog
- grabs attention in the first 2 seconds (a reaction, a surprising line, a question, a strong claim)
- has a payoff or ending (a punchline, reveal, tip, or conclusion)
- is between {min_len} and {max_len} seconds long
- does not overlap with any other moment you pick

Start each moment at the beginning of a sentence and end it after a complete sentence.
Spread picks across the whole vlog when quality is similar.
{hook_rule}

Return ONLY a JSON array of exactly {n} objects, best moment first, each with:
  "start": number (seconds),
  "end": number (seconds),
  "hooks": three on-screen hook options for the first seconds, each max 6 words:
           {{"curiosity": makes them need to know what happens, "bold": a strong claim or reaction,
             "story": sets up the story}},
  "hook_pick": which of the three is strongest: "curiosity", "bold" or "story",
  "title": YouTube title, max 60 characters, no hashtags,
  "thumb_line1": thumbnail text line 1, max 3 words,
  "thumb_line2": thumbnail text line 2, max 3 words (the punchy part),
  "why": one short sentence on why this moment works,
  "hashtags": array of 3 hashtags without the # sign

{context}TRANSCRIPT
{transcript}
"""


def _moment_prompt(transcript, n, context, extra):
    lines = [f"[{s['s']:.1f}-{s['e']:.1f}] {s['text']}" for s in transcript["segments"]]
    return PICK_PROMPT.format(
        hook_rule=HOOK_RULE, duration=fmt_mmss(transcript["duration"]), n=n, min_len=MIN_LEN + 5, max_len=MAX_LEN,
        transcript="\n".join(lines), context=vlog_context_block(context) + (extra and extra + "\n"),
    )


def creator_wishes(taken=(), rejected=(), note=""):
    """Prompt lines for what the creator already chose, didn't like, or asked for."""
    span = lambda m: f"{m['start']:.1f}-{m['end']:.1f}s"  # noqa: E731
    extra = ""
    if taken:
        extra += "ALREADY USED, never overlap these: " + ", ".join(span(m) for m in taken) + "\n"
    if rejected:
        extra += ("THE CREATOR DIDN'T LIKE these picks, choose something different: "
                  + ", ".join(span(m) for m in rejected) + "\n")
    if note.strip():
        extra += ("WHAT THE CREATOR WANTS (follow it closely; if they mention a time like 3:20, the moment "
                  f"must include that time): {note.strip()[:1000]}\n")
    return extra


def _as_list(raw):
    if isinstance(raw, dict):
        raw = next((v for v in raw.values() if isinstance(v, list)), [])
    return raw if isinstance(raw, list) else []


def pick_moments(transcript, n, progress=lambda pct, msg: None, context=None, note="", taken=()):
    """The n best moments. `note` is the creator's instructions; `taken` are moments the creator
    chose themselves (never overlapped)."""
    if n <= 0:
        return []
    progress(10, "Reading the whole transcript")
    raw = ai_json(_moment_prompt(transcript, n + (2 if taken else 0), context, creator_wishes(taken, (), note)),
                  progress, busy_hint=(
        "Your transcript is saved, so just click Make my Shorts again in a few minutes with the same "
        "video; it will skip straight to finding moments."))
    progress(80, "Choosing the best moments")
    try:
        picked = clean_moments(_as_list(raw), transcript, n + (2 if taken else 0))
    except RuntimeError:
        if taken:  # the creator's own moments still make a job worth finishing
            return []
        raise
    kept = [m for m in picked if not any(overlaps(m, t) for t in taken)]
    if len(kept) < len(picked):
        print(f"  {len(picked) - len(kept)} of those dropped, they overlap your must-have moments.")
    return kept[:n]


def clean_moments(raw, transcript, n):
    """Snap AI picks to real word boundaries, enforce length, drop overlaps.

    Prints each suggestion and what happened to it, so a short count can be explained."""
    words = transcript["words"]
    dur = transcript["duration"]
    picked = []
    print(f"AI suggested {len(raw)} moment(s) for {n} Short(s):")

    def log(m, why):
        try:
            span = f"{fmt_mmss(float(m['start']))}-{fmt_mmss(float(m['end']))}"
        except (KeyError, TypeError, ValueError):
            span = "?"
        title = m.get("title", "") if isinstance(m, dict) else ""
        print(f"  {span} {title!r}: {why}")

    for m in raw:
        if len(picked) == n:
            log(m, "not needed, already have enough")
            continue
        try:
            s, e = float(m["start"]), float(m["end"])
        except (KeyError, TypeError, ValueError):
            log(m, "dropped, no usable start/end times")
            continue
        inside = [w for w in words if w["s"] >= s - 0.4 and w["e"] <= e + 0.6]
        if not inside:
            log(m, "dropped, nobody speaks in it")
            continue
        s = max(0.0, inside[0]["s"] - 0.15)
        # stay under MAX_LEN, ending on a finished word
        inside = [w for w in inside if w["e"] - s <= MAX_LEN - 0.4] or inside[:1]
        e = min(dur, inside[-1]["e"] + 0.35)
        if e - s < MIN_LEN:
            log(m, f"dropped, only {e - s:.0f}s from first to last spoken word (needs {MIN_LEN}s)")
            continue
        if any(not (e <= p["start"] or s >= p["end"]) for p in picked):
            log(m, "dropped, overlaps a moment already chosen")
            continue
        log(m, f"kept as {fmt_mmss(s)}-{fmt_mmss(e)}")
        picked.append({
            "start": round(s, 2), "end": round(e, 2),
            **hook_fields(m, said_between(transcript, s, e)),
            "title": str(m.get("title", "New Short"))[:90],
            "thumb_line1": str(m.get("thumb_line1", ""))[:30],
            "thumb_line2": str(m.get("thumb_line2", ""))[:30],
            "why": str(m.get("why", "")),
            "hashtags": [re.sub(r"[^\w]", "", h) for h in m.get("hashtags", [])][:5],
        })
    if not picked:
        raise RuntimeError("Couldn't find usable moments. Try a different vlog or fewer Shorts.")
    return picked


def overlaps(a, b):
    return a["start"] < b["end"] and b["start"] < a["end"]
