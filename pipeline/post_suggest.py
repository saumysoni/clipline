"""
AI ideas for a Short's YouTube title or Instagram caption: "Generate ideas" on the editor card's YouTube and Instagram
tabs (js/post-text.js, web/post_text.py). Three options; the creator picks one and can still edit it.

The same rule as hooks: every fact must come from what is said in the Short (HOOK_RULE), and an idea with a number
that isn't said is dropped ("I lost $2,000" from a clip that never says it).
"""
import re

from pipeline.ai import ai_json
from pipeline.hooks import HOOK_RULE, _numbers
from pipeline.text import said_between, without_emoji
from pipeline.vlog_context import vlog_context_block

TITLE_MAX = 95  # the title field's limit (YouTube allows 100)
CAPTION_MAX = 600

PROMPTS = {
    "title": """You write YouTube Shorts titles. Write three different titles for this Short, each max 60 characters,
in the creator's voice: something people want to tap. Different angles (a question, a reaction, what happens).
No hashtags, no quotes around the title, no ALL CAPS words, at most one emoji, not a copy of the current title.
{rule}
Return ONLY a JSON object: {{"items": ["...", "...", "..."]}}

Current title: {title}
On-screen hook: {hook}
{context}WHAT IS SAID IN THIS SHORT
{said}
""",
    "caption": """You write Instagram Reel captions. Write three different captions for this Reel, in the creator's own
voice (first person, casual), each 1 to 3 short sentences and max 300 characters. Make people stop and comment: a
small story, a reaction, or a question to the viewer. One or two emoji are fine. No hashtags (they're added
separately), no links, and don't repeat the on-screen hook word for word.
{rule}
Return ONLY a JSON object: {{"items": ["...", "...", "..."]}}

Title: {title}
On-screen hook: {hook}
{context}WHAT IS SAID IN THIS SHORT
{said}
""",
}


def _clean(kind, text):
    text = " ".join(str(text or "").split()) if kind == "title" else str(text or "").strip()
    text = text.strip('"“”').strip()
    text = re.sub(r"(^|\s)#\w+", "", text).strip()  # hashtags have their own field
    limit = TITLE_MAX if kind == "title" else CAPTION_MAX
    return text if len(text) <= limit else ""


def suggest_post_text(kind, short, transcript=None, context=None):
    """Three title ("title") or caption ("caption") ideas for a Short. transcript may be None (its file is gone):
    then the ideas come from the title, hook and why. Raises RuntimeError in plain words."""
    if kind not in PROMPTS:
        raise RuntimeError("Pit Crew can only write titles and captions.")
    said = said_between(transcript, short["start"], short["end"]) if transcript else ""
    known = said or " ".join(str(short.get(k) or "") for k in ("title", "hook", "why"))
    hook = short.get("hook", "") if short.get("hook_mode", "text") != "none" else ""
    raw = ai_json(PROMPTS[kind].format(
        rule=HOOK_RULE.replace("Hooks", "Titles" if kind == "title" else "Captions"),
        title=short.get("title", ""), hook=hook or "(none)", context=vlog_context_block(context),
        said=said[:4000] or "(the words aren't available: use the title and hook)"), temperature=0.9)
    items = raw.get("items") if isinstance(raw, dict) else raw
    said_numbers, seen, out = _numbers(known), {str(short.get("title", "")).strip().lower()}, []
    for it in items if isinstance(items, list) else []:
        text = _clean(kind, it)
        if not text or text.lower() in seen:
            continue
        if _numbers(text) - said_numbers:
            print(f"  Dropped the {kind} idea {text!r}: it has a number that isn't said in the Short.")
            continue
        if kind == "title" and not without_emoji(text).strip():
            continue
        seen.add(text.lower()); out.append(text)
    if not out:
        raise RuntimeError(f"Couldn't write {kind} ideas that stick to what's said in this Short. "
                           "Press Generate ideas again, or write your own.")
    return out[:3]
