"""
Private beta: with INVITE_ONLY=1, only invited emails can make a Pit Crew account (email sign-up and Google sign-in).
People who already have an account are never affected. The list is a plain text file, one email per line (# for
notes), read on every sign-up, so inviting someone needs no restart: deploy/invite.sh adds a line.
File: INVITES_FILE, else invites.txt next to the database (data/, never in git).
Why: the beta server is small and YouTube gives the whole app 100 uploads a day, so sign-ups are by invitation until
Google and Meta approve the app.
"""
import os
from pathlib import Path

from accounts.db import DB_PATH


def invite_only():
    return os.getenv("INVITE_ONLY", "").strip().lower() in ("1", "true", "yes")


def invites_file():
    return Path(os.getenv("INVITES_FILE") or DB_PATH.parent / "invites.txt")


def invited(email):
    """True if this email may make an account (always, unless INVITE_ONLY is on)."""
    if not invite_only():
        return True
    email = (email or "").strip().lower()
    try:
        lines = invites_file().read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    return email in {ln.split("#", 1)[0].strip().lower() for ln in lines}


def not_invited_message():
    support = os.getenv("SUPPORT_EMAIL", "").strip()
    return ("Pit Crew is in private beta, and this email isn't on the invite list yet."
            + (f" Ask for an invite at {support}." if support else " Ask the person who told you about Pit Crew for an invite."))
