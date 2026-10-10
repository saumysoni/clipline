"""
Confirm your email: after signing up with email + password, Pit Crew emails a link (<APP_URL>/#verify=<token>, valid
48 hours; only its hash is stored). Opening it marks the email confirmed. Google sign-ins come confirmed by Google.

Pit Crew works before confirming; only the notice emails (Shorts ready, stopped, posting failed: web/notices.py) wait
for it, so nobody gets mail from an account someone else made with their address. The page shows a banner with Resend.
"""
import os
import threading
import time
import traceback

from flask import g, jsonify, request

from accounts import db, mail

from web.server import app


SENT = {}  # user id -> times a confirmation link was sent recently


def send_verification(user, base_url):
    """Email a fresh link (in a background thread: SMTP can take seconds). No SMTP = the link is printed."""
    link = f"{base_url.rstrip('/')}/#verify={db.new_email_verification(user['id'])}"
    text = (f"Welcome to Pit Crew! Confirm your email so Pit Crew can tell you when your Shorts are ready:\n\n{link}\n\n"
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
