"""
The public pages anyone can open without an account: the homepage (/welcome), the privacy policy (/privacy), the
terms (/terms) and how to delete your data (/data-deletion). Google's app verification, YouTube's API audit and
Meta's app review all ask for these, on the app's own domain.

The texts live in static/legal/*.html. Values that depend on how this server is set up are filled in here, so the
policy always says what the server really does: the support email, who runs Pit Crew (OPERATOR_NAME), how long files
are kept (web/retention.py's settings), and which AI services get your content (AI_* keys in .env).
Change UPDATED when you change what a policy says.
"""
import html
import os
import re

from flask import Response, abort, request

from settings import ROOT

from web.retention import keep_draft, keep_original, keep_posted, keep_transcript
from web.server import app

UPDATED = "October 25, 2026"
LEGAL = ROOT / "static" / "legal"
TITLES = {"welcome": ("Pit Crew: Shorts and Reels from your vlogs", "Turn one long vlog into finished YouTube Shorts "
                      "and Instagram Reels, post them, and see how they do."),
          "privacy": ("Privacy policy · Pit Crew", "What Pit Crew collects, why, who it's shared with, and how to delete it."),
          "terms": ("Terms of use · Pit Crew", "The rules for using Pit Crew."),
          "data-deletion": ("Delete your data · Pit Crew", "How to delete your Pit Crew account and everything in it.")}


def _span(seconds, unit):
    n = seconds / (3600 if unit == "hours" else 86400)
    return "kept until you delete it" if not n else f"{n:g} {unit if n != 1 else unit[:-1]}"


def _values():
    support = os.getenv("SUPPORT_EMAIL", "").strip()
    ai = []
    if os.getenv("GEMINI_API_KEY"):
        ai.append("Google (the Gemini API)")
    if os.getenv("OPENAI_API_KEY"):
        ai.append("OpenAI (the OpenAI API)")
    paid = os.getenv("GEMINI_PAID", "").strip().lower() in ("1", "true", "yes")
    return {
        "SUPPORT": support or "the email address on the Help link in Pit Crew",
        "SUPPORT_LINK": f'<a href="mailto:{html.escape(support)}">{html.escape(support)}</a>' if support else "the Help link in Pit Crew",
        "OPERATOR": os.getenv("OPERATOR_NAME", "").strip() or "the Pit Crew team",
        "SITE": (os.getenv("APP_URL") or "").rstrip("/") or "this website",
        "UPDATED": UPDATED,
        "AI": " and ".join(ai) or "an AI service",
        "AI_NOTE": ("We use Google's paid Gemini API plan, under which Google doesn't use what we send to improve its products."
                    if paid else
                    "During the beta we use Google's free Gemini API plan, under which Google may use what we send to "
                    "improve its products (people at Google may review it). Don't upload a vlog you wouldn't want reviewed. "
                    "We'll update this page when we move to the paid plan, which doesn't allow that. On the free plan "
                    "nothing from your YouTube account goes to Gemini: no channel numbers, and not the details of a vlog "
                    "read from its YouTube link (Pit Crew's read on Analytics is then written without AI)."),
        "KEEP_ORIGINAL": _span(keep_original(), "hours"),
        "KEEP_DRAFT": _span(keep_draft(), "days"),
        "KEEP_POSTED": _span(keep_posted(), "days"),
        "KEEP_TRANSCRIPT": _span(keep_transcript(), "days"),
    }


# Only the homepage has its own styles and script (its animations); the other pages are plain text.
EXTRAS = {"welcome": ('<link rel="stylesheet" href="/static/legal/home.css">',
                      '<script src="/static/legal/home.js" defer></script>')}


def render(name, extra=None):
    title, desc = TITLES[name]
    vals = {**_values(), **(extra or {})}
    raw = {"SUPPORT_LINK", "STATUS"}  # already HTML
    fill = lambda text: re.sub(r"\{\{(\w+)\}\}", lambda m: vals[m.group(1)] if m.group(1) in raw
                               else html.escape(vals.get(m.group(1), m.group(0))), text)
    body = fill((LEGAL / f"{name}.html").read_text(encoding="utf-8"))
    page = (LEGAL / "page.html").read_text(encoding="utf-8")
    page = page.replace("{{TITLE}}", html.escape(title)).replace("{{DESC}}", html.escape(desc)).replace("{{BODY}}", body)
    head, scripts = EXTRAS.get(name, ("", ""))
    page = page.replace("{{HEAD}}", head).replace("{{SCRIPTS}}", scripts).replace("{{PAGE}}", name)
    return Response(page, mimetype="text/html", headers={"Cache-Control": "no-cache"})


def _day(d):
    return f"{d:%B} {d.day}, {d.year}"


@app.get("/welcome")
def welcome():
    return render("welcome")


@app.get("/privacy", defaults={"page": "privacy"})
@app.get("/terms", defaults={"page": "terms"})
@app.get("/data-deletion", defaults={"page": "data-deletion"})
def legal_page(page):
    if page not in TITLES:
        abort(404)
    extra = None
    if page == "data-deletion":  # ?code=...: a deletion asked through Meta (web/instagram_deletion.py)
        from datetime import datetime, timezone
        from web.instagram_deletion import deletion_status
        code = request.args.get("code", "")
        done = deletion_status(code)
        extra = {"STATUS": "" if not code else (
            f'<p class="lg-note"><b>Request {html.escape(code)}: done.</b> Pit Crew deleted the data of the Instagram '
            f'account on {_day(datetime.fromtimestamp(done["done_at"], timezone.utc))}.</p>' if done else
            f'<p class="lg-note">There is no deletion request with the code {html.escape(code[:40])}. Check the code, '
            f'or ask us: {_values()["SUPPORT_LINK"]}.</p>')}
    return render(page, extra or {"STATUS": ""})
