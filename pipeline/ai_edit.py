"""
AI Edit (the editor's first tool, js/ai-edit.js, web/ai_edit.py): changing which parts of the moment a Short keeps.
Everything here returns pieces to keep or cuts to make (pipeline/pieces.py); nothing is rendered here. (The AI's
suggested cuts and "Make it shorter" (the AI kept the sentences for 30 / 45 / 60 s) were removed in October 2026: the
creator didn't choose the cuts, and the result wasn't reliable.)

  - pauses(): silences between words (and before the first / after the last word), cut down to a short breath.
    Two strengths: "long" (pauses over 0.7 s) and "tight" (over 0.35 s: a faster pace).
  - fillers(): "um", "uh", "erm"... said on their own (Whisper leaves many out, so there may be none).
  - honest_hooks(): after a cut, a hook may quote a number that's no longer said: that hook is dropped (HOOK_RULE).
"""
import re

from pipeline.hooks import _numbers

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
