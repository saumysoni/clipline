"""
Writing a whole vlog's YouTube details from its transcript: three title ideas, a description with timestamped
chapters, search tags, and two short lines for its thumbnail. Every part is a suggestion the creator edits
before uploading (web/vlog_upload.py). No web code here.
"""
from pipeline.ai import ai_json
from pipeline.text import fmt_mmss

MAX_TITLE = 100        # YouTube's limits
MAX_DESCRIPTION = 5000
MAX_TAGS_CHARS = 500
MIN_CHAPTER_GAP = 10   # YouTube: chapters at least 10 s long, at least 3 of them, the first at 0:00


META_PROMPT = """You are helping a YouTube vlogger upload a full vlog ({duration}). Below is its timestamped
transcript. Write the YouTube details, true to what is actually said and shown; never invent places,
people or events that aren't in the transcript.
{context}
Return ONLY a JSON object:
{{
  "titles": three different title ideas, each max 70 characters, curiosity-driven but honest, no clickbait
            lies, no hashtags, no ALL CAPS sentences,
  "description": 2 short paragraphs a viewer reads under the video (what happens, why watch), first person
                 as the creator, max 600 characters, no hashtags, no links, no chapter list,
  "chapters": 4 to 12 chapters spread over the whole vlog, each {{"t": start second (number), "title": max 40
              characters}}; the first starts at 0 ("Intro" or a better name); each at least 30 seconds after
              the previous one and at a real change of topic or place,
  "tags": 8 to 15 YouTube search tags (places, activities, topics; lower case; no # sign),
  "hashtags": 3 hashtags without the # sign,
  "thumb_line1": thumbnail text line 1, 1-3 words (or ""),
  "thumb_line2": thumbnail headline, 1-3 punchy words
}}

TRANSCRIPT
{transcript}
"""


def _transcript_lines(tr, max_chars=60000):
    lines, used = [], 0
    for s in tr.get("segments") or []:
        line = f"[{fmt_mmss(s['s'])}] {s['text'].strip()}"
        used += len(line) + 1
        if used > max_chars:  # very long vlogs: keep the start of every stretch rather than cutting the end
            break
        lines.append(line)
    return "\n".join(lines)


def clean_chapters(chapters, duration):
    """YouTube's chapter rules: first at 0:00, increasing, >= MIN_CHAPTER_GAP apart, at least 3; else none."""
    out = []
    for c in sorted(chapters or [], key=lambda c: float(c.get("t") or 0) if isinstance(c, dict) else 0):
        if not isinstance(c, dict):
            continue
        try:
            t = max(0, int(float(c.get("t") or 0)))
        except (TypeError, ValueError):
            continue
        title = " ".join(str(c.get("title") or "").split())[:60]
        if not title or (duration and t > duration - MIN_CHAPTER_GAP):
            continue
        if not out:
            t = 0  # YouTube: the first chapter starts at 0:00
        elif t - out[-1]["t"] < MIN_CHAPTER_GAP:
            continue
        out.append({"t": t, "title": title})
    return out if len(out) >= 3 else []


def stamp(sec):
    """A chapter time as YouTube reads it: 4:05, or 1:02:09 past an hour."""
    sec = int(sec)
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def compose_description(text, chapters, hashtags=()):
    """The description as it goes to YouTube: the text, the chapter list (which YouTube turns into chapters), hashtags."""
    parts = [text.strip()]
    if chapters:
        parts.append("\n".join(f"{stamp(c['t'])} {c['title']}" for c in chapters))
    tags = " ".join("#" + h.strip().lstrip("#").replace(" ", "") for h in hashtags if h and h.strip())
    if tags:
        parts.append(tags)
    return "\n\n".join(p for p in parts if p)[:MAX_DESCRIPTION]


def clean_tags(tags):
    out, used = [], 0
    for t in tags or []:
        t = " ".join(str(t).replace(",", " ").replace("#", "").split()).lower()[:60]
        if not t or t in out or used + len(t) + 2 > MAX_TAGS_CHARS:
            continue
        out.append(t)
        used += len(t) + 2
    return out


def write_vlog_meta(tr, context=None, progress=lambda pct, msg: None):
    """{"titles", "description", "chapters", "tags", "thumb_line1", "thumb_line2"} for the vlog."""
    ctx = ""
    if context and context.get("note"):
        ctx = f"What the creator says about it: {context['note'][:800]}\n"
    prompt = META_PROMPT.format(duration=fmt_mmss(tr.get("duration") or 0), context=ctx, transcript=_transcript_lines(tr))
    raw = ai_json(prompt, progress, temperature=0.5)
    raw = raw if isinstance(raw, dict) else {}
    titles = [" ".join(str(t).split())[:MAX_TITLE] for t in (raw.get("titles") or []) if str(t).strip()][:3]
    chapters = clean_chapters(raw.get("chapters"), tr.get("duration") or 0)
    hashtags = [str(h).strip().lstrip("#") for h in (raw.get("hashtags") or []) if str(h).strip()][:3]
    text = str(raw.get("description") or "").strip()[:1500]
    return {"titles": titles or ["My new vlog"], "text": text, "chapters": chapters, "hashtags": hashtags,
            "description": compose_description(text, chapters, hashtags), "tags": clean_tags(raw.get("tags")),
            "thumb_line1": str(raw.get("thumb_line1") or "")[:30], "thumb_line2": str(raw.get("thumb_line2") or "")[:30]}
