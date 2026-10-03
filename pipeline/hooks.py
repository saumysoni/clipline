"""
Hooks: the on-screen text in a Short's first seconds (3 styles to choose from, or none).

Hooks must be true: every prompt carries HOOK_RULE, and hook_fields() drops any hook with a number
that isn't said in the moment.
"""
import re

from pipeline.ai import ai_json
from pipeline.text import said_between, without_emoji
from pipeline.vlog_context import vlog_context_block


HOOK_STYLES = ("curiosity", "bold", "story")


HOOK_RULE = ("Hooks may tease or reframe, in the creator's tone, but every fact in them (numbers, money, places, "
             "events) must come from what is said in the moment. Never invent anything.")


def _numbers(text):
    """Numbers in a text, written the same way ("5 ,000" and "5,000" both become 5000)."""
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", re.sub(r"\s+,", ",", text or ""))}


def _hook_dict(value):
    """Hook options as {style: text}, whatever shape the AI used: an object, a list holding an object
    (seen from OpenAI), a list of {"style", "text"} objects, or a plain list of texts."""
    if isinstance(value, dict):
        return {str(k).strip().lower(): v for k, v in value.items()}
    out = {}
    if isinstance(value, list):
        for k, item in enumerate(value):
            if isinstance(item, dict):
                if "text" in item or "hook" in item:
                    out[str(item.get("style") or item.get("type") or HOOK_STYLES[k % 3]).lower()] = \
                        item.get("text") or item.get("hook")
                else:
                    out.update(_hook_dict(item))
            elif isinstance(item, str) and k < len(HOOK_STYLES):
                out[HOOK_STYLES[k]] = item
    elif isinstance(value, str):
        out["custom"] = value
    return out


def hook_fields(raw, said="", fallback=None):
    """The hook options from an AI answer, keeping only honest ones: a hook with a number that isn't
    said in the moment ("I lost $2,000" from a clip that never says it) is dropped.
    Returns hooks (style -> text), hook_style, hook (the chosen text) and hook_mode."""
    raw = raw if isinstance(raw, dict) else {}
    fb = fallback or {}
    said_numbers = _numbers(said)
    hooks = {}
    offered = _hook_dict(raw.get("hooks"))
    single = " ".join(str(raw.get("hook") or "").split())[:60]
    for style, text in [*((k, offered.get(k)) for k in HOOK_STYLES), ("custom", single)]:
        text = " ".join(str(text or "").split())[:60]
        if not text or text in hooks.values():
            continue
        if _numbers(text) - said_numbers:
            print(f"  Dropped the {style} hook {text!r}: it has a number that isn't said in the moment.")
            continue
        hooks[style] = text
    if not hooks and fb.get("hooks"):
        return {k: fb[k] for k in ("hooks", "hook_style", "hook", "hook_mode") if k in fb}
    pick = str(raw.get("hook_pick", "")).lower()
    style = pick if pick in hooks else next(iter(hooks), "custom")
    hook = hooks.get(style) or fb.get("hook", "")
    return {"hooks": hooks, "hook_style": style, "hook": hook, "hook_mode": "text" if hook else "none"}


HOOK_PROMPT = """You write on-screen hooks for a YouTube Short: the text shown in the first seconds that makes
people keep watching. Write three, each max 6 words:
  "curiosity": makes them need to know what happens,
  "bold": a strong claim or reaction,
  "story": sets up the story.
{hook_rule}
{note}Return ONLY a JSON object: {{"hooks": {{"curiosity": ..., "bold": ..., "story": ...}},
  "hook_pick": the strongest: "curiosity", "bold" or "story"}}

Short title: {title}
{context}WHAT IS SAID IN THIS SHORT
{said}
"""


def rewrite_hooks(transcript, moment, note="", context=None):
    """Three fresh hook options for a Short, optionally nudged by the creator ("funnier")."""
    said = said_between(transcript, moment["start"], moment["end"])
    raw = ai_json(HOOK_PROMPT.format(
        hook_rule=HOOK_RULE, title=moment.get("title", ""), said=said[:4000] or "(no talking in this Short)",
        note=f"The creator asks: {note.strip()[:300]}\n" if note.strip() else "",
        context=vlog_context_block(context)), temperature=0.8)
    out = hook_fields(raw, said)
    if not out.get("hooks"):
        raise RuntimeError("Couldn't write new hooks that stick to what's said in this Short. Try again, "
                           "or type your own hook.")
    return out


def hook_to_lines(hook):
    """A hook split over the thumbnail's two lines as evenly as possible (line 2 is the big block)."""
    text = re.sub(r"\s+([?!.,])", r"\1", without_emoji(hook))
    words = text.split()
    if len(words) <= 2:
        return "", text
    k = min(range(1, len(words)), key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))))
    return " ".join(words[:k]), " ".join(words[k:])
