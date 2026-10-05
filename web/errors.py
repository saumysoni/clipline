"""
Turning what went wrong inside Pit Crew (an FFmpeg log, an AI service's reply, a Python message) into one plain
sentence a creator can act on. The full text is kept in job["error_detail"] and printed in the terminal.
"""
import re


def plain_error(raw, doing=""):
    """A short, plain message for a failed vlog. `doing` is the stage it stopped at ("Editing Shorts")."""
    text = str(raw or "").strip()
    low = text.lower()
    where = f" while {doing[0].lower()}{doing[1:]}" if doing else ""
    if any(k in low for k in ("503", "unavailable", "high demand", "overloaded")):
        return "The AI service was too busy" + where + ". Upload the vlog again in a few minutes."
    if any(k in low for k in ("429", "resource_exhausted", "quota", "rate limit")):
        return "The AI's free limit was reached for now. Upload the vlog again later, or tomorrow."
    if "metadata_errors" in low:
        return "An older version of Pit Crew couldn't read this video's sound. That's fixed now: upload the vlog again."
    if "command failed: ffmpeg" in low or "ffmpeg" in low and len(text) > 160:
        return "Pit Crew's video editor stopped" + where + ". Upload the vlog again; if it keeps happening, tell us."
    if "no space left" in low:
        return "The computer ran out of storage space. Free some space, then upload the vlog again."
    technical = len(text) > 220 or re.search(r"\{'|Traceback|Error\(|0x[0-9a-f]{6,}|\bat 0x", text)
    if not text or technical:
        return "Something went wrong" + where + ". Upload the vlog again; if it keeps happening, tell us."
    return text
