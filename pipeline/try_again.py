"""
Try again: replace one Short with a different moment, optionally guided by the creator's note
("make it longer", "the part at 3:20").
"""
import re

from pipeline.ai import ai_json
from pipeline.constants import MAX_LEN, MIN_LEN
from pipeline.hooks import HOOK_RULE
from pipeline.manual_moment import MANUAL_MAX, MANUAL_MIN, moment_text, snap_moment
from pipeline.moments import _as_list, clean_moments, creator_wishes, overlaps
from pipeline.text import fmt_mmss, said_between
from pipeline.vlog_context import vlog_context_block


REDO_PROMPT = """You are an expert short-form video editor for a YouTube creator. The creator wants to change
one Short made from their vlog ({duration} long).

{current}{wishes}
Decide what they want:
- "adjust": they want THIS Short changed (longer, shorter, a set length, start earlier, end later, include
  what comes before or after). Keep what's in it now and move the start and end. Follow a requested length
  exactly, even if part of it has no talking.
- "new": they want a different moment. Pick moments that make sense on their own, grab attention in the
  first 2 seconds and have a payoff.
Moments are {min_len}-{max_len} seconds long unless the creator asks for another length (never over 180).
Start at the beginning of a sentence and end after a complete sentence where there is talking.
{hook_rule}

Return ONLY a JSON object:
{{"change": "adjust" or "new",
  "options": up to 3 moments, best first, each {{"start": seconds, "end": seconds,
    "hooks": {{"curiosity": ..., "bold": ..., "story": ...}} three on-screen hooks, max 6 words each,
    "hook_pick": the strongest of the three, "title": YouTube title, max 60 characters, no hashtags,
    "thumb_line1": max 3 words, "thumb_line2": max 3 words (the punchy part),
    "why": one short sentence, "hashtags": array of 3 hashtags without the # sign}}}}

{context}TRANSCRIPT
{transcript}
"""


LENGTH_RE = re.compile(r"(\d+(?:\.\d+)?)\s*-?\s*(s|secs?|seconds?|m|mins?|minutes?)\b", re.I)


def requested_length(note):
    """The length in seconds a creator asks for ("make it 30 sec", "1 minute"), or None.
    With several lengths ("this 13 sec clip, make it 30 sec"), the one after make it/to/into/be wins."""
    note = (note or "").lower()
    if re.search(r"half (a|of a) minute", note):
        return 30.0
    found = []
    for m in LENGTH_RE.finditer(note):
        sec = float(m.group(1)) * (60 if m.group(2).startswith("m") else 1)
        aimed = re.search(r"\b(make it|to|into|be|as|about|around|of)\s+(a\s+)?$", note[:m.start()].rstrip() + " ")
        found.append((bool(aimed), sec))
    if not found:
        return 60.0 if re.search(r"\b(a|one) minute\b", note) else None
    aimed = [sec for ok, sec in found if ok]
    return aimed[0] if aimed else found[-1][1]


def stretch(current, target, duration, taken):
    """The current Short made `target` seconds long: the end moves first, then the start, never into
    another Short or past the video. Shortening keeps the start."""
    s, e = current["start"], current["end"]
    target = max(MANUAL_MIN, min(target, MANUAL_MAX, duration))
    if e - s >= target:
        return s, s + target
    after = min([t["start"] for t in taken if t["start"] >= e - 0.5] + [duration])
    before = max([t["end"] for t in taken if t["end"] <= s + 0.5] + [0.0])
    e2 = min(after, s + target)
    return max(before, e2 - target), e2


def repick_moment(transcript, taken, rejected, note="", progress=lambda pct, msg: None, context=None,
                  current=None):
    """A new moment for a Short the creator wants changed: adjusted ("make it 30 seconds") or different.

    `taken` are the other Shorts (never overlapped), `rejected` the moments already tried for this Short,
    `note` what the creator asked for (may be empty), `current` the Short as it is now (None for a new one).
    When the creator asked for something, the answer follows it even through parts without talking,
    and a requested length is honoured without the AI if needed. Raises only if nothing fits.
    """
    span = lambda m: f"{m['start']:.1f}-{m['end']:.1f}s"  # noqa: E731
    cur = current if current and not current.get("pending") else None
    lines = [f"[{x['s']:.1f}-{x['e']:.1f}] {x['text']}" for x in transcript["segments"]]
    prompt = REDO_PROMPT.format(
        hook_rule=HOOK_RULE, duration=fmt_mmss(transcript["duration"]), min_len=MIN_LEN + 5, max_len=MAX_LEN,
        current=(f"THIS SHORT NOW: {span(cur)} ({cur['end'] - cur['start']:.0f}s), titled {cur.get('title', '')!r}\n"
                 if cur else "This is a NEW Short, so pick a moment (\"new\").\n"),
        wishes=creator_wishes(taken, [r for r in rejected if not cur or not overlaps(r, cur)], note)
        or "The creator just wants something better.\n",
        context=vlog_context_block(context), transcript="\n".join(lines))
    progress(20, "Reading the transcript again")
    raw, change = {}, "new"
    try:
        raw = ai_json(prompt, progress)
        change = str(raw.get("change", "new")).lower() if isinstance(raw, dict) else "new"
    except RuntimeError:
        if not (note.strip() and cur and requested_length(note)):
            raise  # nothing to fall back on
        print("AI unavailable; making the requested length without it.")
    options = _as_list(raw)
    progress(60, "Choosing the moment")
    free = lambda m: not any(overlaps(m, t) for t in taken)  # noqa: E731

    # A different moment, held to the usual standard (enough talking, sensible length).
    if change != "adjust":
        try:
            strict = [m for m in clean_moments(options, transcript, 3) if free(m)]
        except RuntimeError:
            strict = []
        fresh = [m for m in strict if not any(overlaps(m, r) for r in rejected)]
        if fresh:
            return fresh[0]
        if strict and note.strip():
            return strict[0]

    # The creator asked for something: follow the AI's times as given, even through silence.
    if note.strip() or change == "adjust":
        for o in options:
            try:
                s, e = snap_moment(transcript, float(o["start"]), float(o["end"]))
            except (KeyError, TypeError, ValueError, RuntimeError) as err:
                print(f"  AI option {o!r:.80}: unusable ({err})")
                continue
            m = {"start": s, "end": e, "manual": True,
                 **moment_text(o, cur if change == "adjust" else None, said_between(transcript, s, e), s)}
            if free(m):
                print(f"  Following the creator's request: {fmt_mmss(s)}-{fmt_mmss(e)} ({change}).")
                return m
            print(f"  AI option {fmt_mmss(s)}-{fmt_mmss(e)}: overlaps another Short")

    # Still nothing, but they asked for a length: stretch or trim this Short ourselves.
    target = requested_length(note) if cur else None
    if target:
        s, e = snap_moment(transcript, *stretch(cur, target, transcript["duration"], taken))
        got = e - s
        why = (f"Made {got:.0f} seconds long, as you asked." if abs(got - target) < 2 else
               f"Made {got:.0f} seconds long, the most that fits next to your other Shorts and the video's ends.")
        print(f"  Stretched to {fmt_mmss(s)}-{fmt_mmss(e)} for the requested {target:.0f}s.")
        return {"start": s, "end": e, "manual": True, **moment_text({"why": why}, cur, said_between(transcript, s, e), s)}

    raise RuntimeError("Couldn't find a moment that matches. Use Choose on the video to mark the start and end "
                       "yourself, or describe it differently.")
