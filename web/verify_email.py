"""
Confirm your email: after signing up with email + password, Pit Crew emails a link (<APP_URL>/#verify=<token>, valid
48 hours; only its hash is stored). Opening it marks the email confirmed. Google sign-ins come confirmed by Google.

Nothing works before confirming (gate() in web/accounts.py: only UNCONFIRMED_OK), so every account is a real address
Pit Crew can write to, and nobody can use an address that isn't theirs. The page shows "Check your inbox" with Resend
and Change email, and carries on by itself once the link is opened (also when it's opened on another device).
"""
import os
import sqlite3
import threading
import time
import traceback

from flask import g, jsonify, request
from werkzeug.security import check_password_hash

from accounts import db, mail

from web.server import app


SENT = {}  # user id -> times a confirmation link was sent recently


def send_verification(user, base_url):
    """Email a fresh link (in a background thread: SMTP can take seconds). No SMTP = the link is printed."""
    link = f"{base_url.rstrip('/')}/#verify={db.new_email_verification(user['id'])}"
    text = (f"Welcome to Pit Crew! Confirm your email to start using it:\n\n{link}\n\n"
            f"The link works for {db.VERIFY_HOURS} hours. If you didn't make a Pit Crew account, ignore this email.\n")

    def send():
        if not mail.is_configured():
            print(f"Email isn't set up (SMTP_HOST is empty in .env), so no email was sent. "
                  f"Confirmation link for {user['email']}:\n  {link}")
            return
        try:
            mail.send_email(user["email"], "Confirm your Pit Crew email", text)
        except Exception:  # noqa: BLE001
            print(f"Couldn't send the confirmation email to {user['email']}:")
            traceback.print_exc()
    threading.Thread(target=send, daemon=True).start()


def base_url():
    # In the cloud set APP_URL: the request's own address can be faked, and the link must point at Pit Crew.
    return os.getenv("APP_URL") or request.host_url


@app.post("/api/auth/verify")
def auth_verify():
    """Public (PUBLIC in web/accounts.py): the token is the proof, so it works signed out or in another browser."""
    token = str(request.get_json(force=True).get("token", ""))
    user = db.verify_email(token) if 0 < len(token) <= 200 else None
    if not user:
        return jsonify(error="This confirmation link has expired or was already used. Sign in and press Resend "
                             "to get a new one."), 400
    return jsonify(ok=True, email=user["email"])


@app.post("/api/auth/verify/resend")
def auth_verify_resend():
    user = g.user
    if user["email_verified"]:
        return jsonify(ok=True, message="Your email is already confirmed.")
    now = time.time()
    recent = [t for t in SENT.get(user["id"], []) if now - t < 900]
    if len(recent) >= 3:
        return jsonify(error="We've sent a few links already. Check your inbox and spam, or try again in 15 minutes."), 429
    SENT[user["id"]] = recent + [now]
    send_verification(user, base_url())
    return jsonify(ok=True, message=f"Sent. Check your inbox (and spam) at {user['email']}.")


@app.post("/api/auth/email")
def auth_change_email():
    """A typo at sign-up: change the address of an account that isn't confirmed yet, and send a new link there."""
    from web.accounts import EMAIL_RE  # (accounts imports this file)
    from web.invites import invited, not_invited_message
    user, data = g.user, request.get_json(force=True)
    if user["email_verified"]:
        return jsonify(error="Your email is already confirmed. Change it in Settings."), 400
    email = str(data.get("email", "")).strip().lower()
    if not EMAIL_RE.fullmatch(email) or len(email) > 200:
        return jsonify(error="Type a valid email address.", field="email"), 400
    if user["password_hash"] and not check_password_hash(user["password_hash"], str(data.get("password", ""))):
        return jsonify(error="That's not your password.", field="password"), 400
    if not invited(email):
        return jsonify(error=not_invited_message(), field="email"), 403
    now = time.time()
    recent = [t for t in SENT.get(user["id"], []) if now - t < 900]
    if len(recent) >= 3:
        return jsonify(error="We've sent a few links already. Try again in 15 minutes."), 429
    try:
        db.change_email(user["id"], email)
    except sqlite3.IntegrityError:
        return jsonify(error="There's already an account with this email. Sign in with it instead.", field="email"), 400
    SENT[user["id"]] = recent + [now]
    send_verification(db.user_by_id(user["id"]), base_url())
    return jsonify(ok=True, email=email, message=f"Sent. Check your inbox (and spam) at {email}.")
