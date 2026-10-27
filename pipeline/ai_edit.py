"""
AI Edit (the editor's first tool, js/ai-edit.js, web/ai_edit.py): changing which parts of the moment a Short keeps.
Everything here returns pieces to keep or cuts to make (pipeline/pieces.py); nothing is rendered here.

  - pauses(): silences between words (and before the first / after the last word), cut down to a short breath.
    Two strengths: "long" (pauses over 0.7 s) and "tight" (over 0.35 s: a faster pace).
  - fillers(): "um", "uh", "erm"... said on their own (Whisper leaves many out, so there may be none).
  - shorten(): the AI keeps the sentences that make the best Short of about `target` seconds, in their order.
  - suggest_cuts(): the AI points out parts worth cutting (a false start, a repeat, a slow stretch), each with why.
  - honest_hooks(): after a cut, a hook may quote a number that's no longer said: that hook is dropped (HOOK_RULE).

The AI only reads the Short's words (never anything from YouTube), and every answer is checked against the words.
"""
import re

from pipeline.ai import ai_json
from pipeline.hooks import _numbers
from pipeline.manual_moment import MANUAL_MAX, MANUAL_MIN
from pipeline.pieces import kept, normalize, subtract
from pipeline.text import fmt_mmss

PAD = 0.12  # seconds of quiet kept on each side of speech when a pause is cut (a breath, so it doesn't sound chopped)
PAUSE = {"long": 0.7, "tight": 0.35}
FILLERS = {"um", "umm", "uh", "uhh", "uhm", "erm", "er", "ah", "ahh", "hmm", "hm", "mm", "mhm"}


def _key(w):
    return re.sub(r"[^\w']", "", w["w"].lower())


def words_in(words, moment):
    """The words inside the moment's start..end (cut or not), in order."""
    s, e = float(moment["start"]), float(moment["end"])
    return [w for w in words if s <= (w["s"] + w["e"]) / 2 <= e]


def pauses(words, moment, strength="long"):
    """Cuts that shorten every silence longer than PAUSE[strength] to a breath: [(a, b, seconds saved)]."""
    gap = PAUSE.get(strength, PAUSE["long"])
    s, e = float(moment["start"]), float(moment["end"])
    ws = words_in(words, moment)
    if not ws:
        return []
    edges = [(s, ws[0]["s"])] + [(a["e"], b["s"]) for a, b in zip(ws, ws[1:])] + [(ws[-1]["e"], e)]
    out = []
    for k, (a, b) in enumerate(edges):
        first, last = k == 0, k == len(edges) - 1
        a2, b2 = (a if first else a + PAD), (b if last else b - PAD)  # nothing to keep before the first word / after the last
        if b - a >= gap and b2 - a2 >= 0.15:
            out.append((round(a2, 3), round(b2, 3), round(b2 - a2, 2)))
    return out


def fillers(words, moment):
    """Cuts for filler words said on their own: [(a, b, the word)]."""
    ws, out = words_in(words, moment), []
    for k, w in enumerate(ws):
        if _key(w) in FILLERS:
            a = max(w["s"] - 0.04, ws[k - 1]["e"] if k else w["s"] - 0.04)
            b = min(w["e"] + 0.04, ws[k + 1]["s"] if k + 1 < len(ws) else w["e"] + 0.04)
            out.append((round(a, 3), round(b, 3), w["w"]))
    return out


def sentences(words, moment):
    """The Short's kept words as sentence lines: [{"s", "e", "text"}] (what the AI reads, numbered)."""
    from pipeline.transcribe import sentence_segments  # (pure: no speech model is loaded)
    pieces = kept(moment)
    ws = [w for w in words_in(words, moment) if any(a <= (w["s"] + w["e"]) / 2 <= b for a, b in pieces)]
    return sentence_segments(ws, max_len=8.0, max_gap=0.6) if ws else []


def _lines(lines):
    return "\n".join(f"[{k}] ({fmt_mmss(x['s'])}, {x['e'] - x['s']:.1f}s) {x['text']}" for k, x in enumerate(lines))


SHORTEN_PROMPT = """You are shortening a YouTube Short to about {target} seconds (it is {now:.0f} seconds now).
Below are its sentences, numbered, with when each starts and how long it is.

Keep the sentences that make the best Short of about {target} seconds:
- it must still make sense to someone who hasn't seen the vlog, and keep its payoff (the punchline, reveal or tip)
- the first kept sentence must grab attention in the first 2 seconds
- keep the sentences in their order; drop repeats, false starts, slow set-up and side remarks first
- the kept sentences should add up to between {low} and {high} seconds
{note}
Return ONLY a JSON object: {{"keep": [the numbers of the sentences to keep], "why": one short sentence on what you cut}}

SENTENCES
{lines}
"""


CUTS_PROMPT = """You are suggesting cuts for a YouTube Short ({now:.0f} seconds). Below are its sentences, numbered, with
when each starts and how long it is.

Point out up to 4 parts the creator could cut to make it tighter and more watchable: a false start or a sentence that
is said again, a slow or off-topic stretch, a side remark that breaks the story. Never suggest cutting the payoff, and
never cut so much that it stops making sense. If nothing is worth cutting, return no cuts.

Return ONLY a JSON object: {{"cuts": [{{"from": first sentence number, "to": last sentence number (the same for one),
  "kind": "repeat" | "false start" | "slow" | "off topic", "why": one short sentence for the creator}}]}}

SENTENCES
{lines}
"""


def _span(lines, i, j, moment):
    """Vlog seconds covering sentences i..j: from the end of the one before to the start of the one after (so no
    quiet is left behind), within the moment."""
    s, e = float(moment["start"]), float(moment["end"])
    a = lines[i - 1]["e"] + PAD if i > 0 else s
    b = lines[j + 1]["s"] - PAD if j + 1 < len(lines) else e
    return max(s, min(a, lines[i]["s"])), min(e, max(b, lines[j]["e"]))


def _length(pieces):
    return sum(b - a for a, b in pieces)


def shorten(transcript, moment, target, progress=lambda pct, msg: None, note=""):
    """Pieces to keep for a Short of about `target` seconds: {"keep": [(a, b)], "why", "ai"}. Without the AI (busy, no
    key) the Short is cut at the last sentence that fits, so the creator still gets their length."""
    target = max(MANUAL_MIN, min(float(target), MANUAL_MAX))
    s, e = float(moment["start"]), float(moment["end"])
    lines, now = sentences(transcript["words"], moment), _length(kept(moment))
    if not lines:
        raise RuntimeError("There's no talking in this Short, so Pit Crew can't choose what to keep. Use Trim instead.")
    if now <= target + 1:
        raise RuntimeError(f"This Short is already {now:.0f} seconds long.")
    picked, why, used_ai = None, "", False
    progress(20, "Reading the Short")
    try:
        raw = ai_json(SHORTEN_PROMPT.format(target=round(target), now=now, low=round(target * 0.8), high=round(target * 1.1),
                                            lines=_lines(lines), note=(f"The creator asks: {note.strip()[:300]}\n" if note.strip() else "")),
                      progress, temperature=0.3, timeout=60, busy_waits=[5])
        idx = sorted({int(i) for i in (raw.get("keep") or []) if str(i).lstrip("-").isdigit() and 0 <= int(i) < len(lines)}) \
            if isinstance(raw, dict) else []
        if idx:
            picked, why, used_ai = idx, str(raw.get("why") or "")[:200], True
    except RuntimeError as err:  # (not "e": that's the moment's end)
        print(f"Shortening without the AI ({err}).")
    if not picked:  # no AI: keep from the start, up to the last sentence that fits
        picked, total = [], 0.0
        for k, x in enumerate(lines):
            if picked and total + (x["e"] - x["s"]) > target * 1.05:
                break
            picked.append(k)
            total += x["e"] - x["s"]
        why = f"Kept the first {len(picked)} sentence{'s' if len(picked) != 1 else ''}."
    pieces = normalize([_span(lines, k, k, moment) for k in picked], s, e)
    while len(picked) > 1 and _length(pieces) > target * 1.25:  # the AI kept too much: drop from the end
        picked.pop()
        pieces = normalize([_span(lines, k, k, moment) for k in picked], s, e)
    if _length(pieces) < MANUAL_MIN:
        raise RuntimeError(f"That would leave less than {MANUAL_MIN} seconds. Choose a longer length.")
    return {"keep": pieces, "why": why, "ai": used_ai}


def suggest_cuts(transcript, moment, progress=lambda pct, msg: None):
    """Parts worth cutting, from the AI: [{"start", "end", "seconds", "kind", "why", "text"}] (vlog seconds). Each is
    checked: inside what's kept now, and never leaving the Short under MANUAL_MIN seconds."""
    s, e = float(moment["start"]), float(moment["end"])
    lines, pieces = sentences(transcript["words"], moment), kept(moment)
    if len(lines) < 2:
        return []
    progress(20, "Reading the Short")
    raw = ai_json(CUTS_PROMPT.format(now=_length(pieces), lines=_lines(lines)), progress, temperature=0.3, timeout=60,
                  busy_waits=[5])
    out = []
    for c in (raw.get("cuts") if isinstance(raw, dict) else raw) or []:
        try:
            i, j = int(c.get("from")), int(c.get("to", c.get("from")))
        except (TypeError, ValueError, AttributeError):
            continue
        if not (0 <= i <= j < len(lines)) or j - i + 1 >= len(lines):
            continue
        a, b = _span(lines, i, j, moment)
        left = subtract(pieces, [(a, b)], s, e)
        if _length(left) < MANUAL_MIN or any(a < o["end"] and o["start"] < b for o in out):
            continue
        kind = str(c.get("kind") or "slow").lower()
        out.append({"start": round(a, 3), "end": round(b, 3), "seconds": round(_length(pieces) - _length(left), 1),
                    "kind": kind if kind in ("repeat", "false start", "slow", "off topic") else "slow",
                    "why": " ".join(str(c.get("why") or "").split())[:200],
                    "text": " ".join(x["text"] for x in lines[i:j + 1])[:300]})
    return out


def honest_hooks(moment, said):
    """After a cut: the hook options with no number that isn't said any more. Returns the fields to change (hooks,
    hook, hook_style, hook_mode) and a note for the creator, or ({}, "") when the hook is still true."""
    numbers = _numbers(said)
    hooks = dict(moment.get("hooks") or {})
    good = {k: t for k, t in hooks.items() if not (_numbers(t) - numbers)}
    hook = moment.get("hook", "")
    on = moment.get("hook_mode", "text") != "none" and hook
    if good == hooks and not (on and _numbers(hook) - numbers):
        return {}, ""
    out = {"hooks": good}
    if on and _numbers(hook) - numbers:
        style = next(iter(good), "")
        out.update(hook=good.get(style, ""), hook_style=style or "custom", hook_mode="text" if style else "none")
        return out, ("The hook quoted something that's no longer said, so " +
                     (f"it was changed to “{good[style]}”." if style else "the Short has no text hook now."))
    return out, ""
