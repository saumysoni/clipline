"""
AI suggestions for a whole video's YouTube title, description or tags, with an optional request in the creator's own words
("funnier", "mention the market"). Every option is a suggestion: the creator picks one and can still edit it (web/vlog_suggest.py,
js/vlog-suggest.js). The same rule as hooks: every fact comes from what's said in the video (HOOK_RULE), and an option with a number
that isn't said is dropped. A description's chapter lines are kept as they are: the AI only rewrites the words around them.
"""
import re

from pipeline.ai import ai_json
from pipeline.hooks import HOOK_RULE, _numbers
from pipeline.vlog_meta import MAX_DESCRIPTION, MAX_TITLE, _transcript_lines, clean_tags as clean_vlog_tags

FIELDS = ("title", "description", "tags")
MAX_ASK = 300
_CHAPTER = re.compile(r"^\s*\d{1,2}:\d{2}(?::\d{2})?\b")

PROMPT = """You improve one detail of a creator's full YouTube video before it's uploaded. {what}
{rule}
The creator's request is about style and focus. If it asks for a fact the transcript doesn't support, leave that fact out.
Return ONLY a JSON object: {{"items": {shape}}}

THE CREATOR'S REQUEST
{ask}

THE CURRENT {name}
{current}

WHAT IS SAID IN THE VIDEO
{said}
"""
WHAT = {
    "title": "Write three different titles, each max 70 characters: curiosity-driven but honest, no hashtags, no ALL CAPS sentences.",
    "description": "Write two different versions of the description text, first person as the creator, max 900 characters, "
                   "no links, no timestamps or chapter list (those are kept separately).",
    "tags": "Write two different sets of 8 to 15 YouTube search tags (places, activities, topics; lower case; no # sign).",
}
SHAPE = {"title": '["...", "...", "..."]', "description": '["...", "..."]', "tags": '[["...", "..."], ["...", "..."]]'}


def _split_chapters(description):
    """(the words, the chapter lines) of a description."""
    lines = str(description or "").splitlines()
    return ("\n".join(x for x in lines if not _CHAPTER.match(x)).strip(), "\n".join(x for x in lines if _CHAPTER.match(x)).strip())


def suggest_vlog_text(field, ask, draft, transcript):
    """Options for one field of the draft (title, description, tags); tags come as a list per option. Raises RuntimeError in
    plain words."""
    if field not in FIELDS:
        raise RuntimeError("Pit Crew can only suggest a title, a description or tags.")
    ask = " ".join(str(ask or "").split())[:MAX_ASK]
    tags = draft.get("tags") or []
    body, chapters = _split_chapters(draft.get("description"))
    current = {"title": draft.get("title") or "", "description": body, "tags": ", ".join(tags)}[field]
    said = _transcript_lines(transcript or {}, 30000)
    raw = ai_json(PROMPT.format(what=WHAT[field], rule=HOOK_RULE.replace("Hooks", "Suggestions"), shape=SHAPE[field],
                                ask=ask or "(none: just make it better for viewers)", name=field.upper(),
                                current=current or "(empty)", said=said or "(the words aren't available: use the title and description)"),
                  temperature=0.9)
    items = raw.get("items") if isinstance(raw, dict) else raw
    known = _numbers(said or " ".join([draft.get("title") or "", body]))
    out, seen = [], set()
    for it in items if isinstance(items, list) else []:
        if field == "tags":
            got = clean_vlog_tags(it if isinstance(it, list) else str(it).split(","))
            key = ",".join(got)
            if got and key not in seen:
                seen.add(key); out.append(got)
            continue
        text = " ".join(str(it or "").split()) if field == "title" else str(it or "").strip()
        text = text.strip('"“”').strip()
        if field == "title":
            text = re.sub(r"(^|\s)#\w+", "", text).strip()
        else:
            text = _split_chapters(text)[0]
        if not text or text.lower() in seen or text == current or _numbers(text) - known:
            continue
        if field == "description" and chapters:
            text = (text + "\n\n" + chapters)
        if len(text) > (MAX_TITLE if field == "title" else MAX_DESCRIPTION):
            continue
        seen.add(text.lower()); out.append(text)
    if not out:
        raise RuntimeError("Couldn't write suggestions that stick to what's said in this video. Try again, or ask for something else.")
    return out[:3]
