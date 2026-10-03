"""
The creator's own title/description/tags for the vlog, turned into guidance for the AI.
"""



def vlog_context_block(context):
    """The creator's own title/description/tags, as extra guidance for the AI."""
    if not context:
        return ""
    parts = []
    if context.get("title"):
        parts.append(f"Title: {context['title'].strip()}")
    if context.get("description"):
        parts.append("Description:\n" + context["description"].strip()[:3000])
    if context.get("tags"):
        parts.append("Tags: " + ", ".join(context["tags"][:30]))
    if not parts:
        return ""
    return ("ABOUT THIS VLOG (written by the creator)\n" + "\n".join(parts) + "\n\n"
            "Use this to understand what the vlog is about, to spell names of people and places correctly "
            "(the transcript may misspell them), and to write titles and hooks in the creator's own tone. "
            "Never copy links, sponsor codes or timestamps from the description.\n\n")
