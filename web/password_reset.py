"""
Forgot password: email a one-time reset link (valid 1 hour), and set a new password from it.
The link is <APP_URL>/#reset=<token>; the page shows "Choose a new password" for it.
"""
import os
import threading
import time
import traceback

from flask import jsonify, request
from werkzeug.security import generate_password_hash

from accounts import db, mail

from web.accounts import EMAIL_RE, start_session
from web.server import app


ASKED = {}  # email -> times reset links were asked for recently


def app_url():
    # In the cloud set APP_URL: the request's own address can be faked, and the link must point at Pit Crew.
    return (os.getenv("APP_URL") or request.host_url).rstrip("/")


def send_reset_email(email, link):
    """Runs in a background thread, so the reply doesn't reveal (by taking longer) whether the account exists."""
    text = (f"Someone (hopefully you) asked to reset the password for your Pit Crew account.\n\n"
            f"Choose a new password here:\n{link}\n\n"
            f"The link works once, for {db.RESET_HOURS} hour. If you didn't ask for this, ignore this email: "
            f"your password stays the same.\n")
    if not mail.is_configured():
        print(f"Email isn't set up (SMTP_HOST is empty in .env), so no email was sent. "
              f"Password reset link for {email}:\n  {link}")
        return
    try:
        mail.send_email(email, "Reset your Pit Crew password", text)
        print(f"Sent a password reset link to {email}.")
    except Exception:
        print(f"Couldn't send the password reset email to {email}:")
        traceback.print_exc()


@app.post("/api/auth/forgot")
def auth_forgot():
    email = str(request.get_json(force=True).get("email", "")).strip().lower()
    if not EMAIL_RE.fullmatch(email) or len(email) > 200:
        return jsonify(error="Type the email address you signed up with.", field="email"), 400
    done = jsonify(ok=True, message="If there's a Pit Crew account for this email, a reset link is on its way. "
                                    "Check your inbox (and spam). The link works for 1 hour.")
    now = time.time()
    recent = [t for t in ASKED.get(email, []) if now - t < 900]
    if len(recent) >= 3:  # same answer, no email: stops someone flooding an inbox
        return done
    ASKED[email] = recent + [now]
    user = db.user_by_email(email)
    if user:
        link = f"{app_url()}/#reset={db.new_password_reset(user['id'])}"
        threading.Thread(target=send_reset_email, args=(user["email"], link), daemon=True).start()
    return done


@app.post("/api/auth/reset")
def auth_reset():
    data = request.get_json(force=True)
    token, password = str(data.get("token", "")), str(data.get("password", ""))
    if len(password) < 8:
        return jsonify(error="Choose a password with at least 8 characters.", field="password"), 400
    if len(password) > 200:
        return jsonify(error="That password is too long.", field="password"), 400
    user = db.reset_password(token, generate_password_hash(password)) if 0 < len(token) <= 200 else None
    if not user:
        return jsonify(error="This reset link has expired or was already used. Use Forgot password to get a "
                             "new one.", expired=True), 400
    start_session(user)
    return jsonify(ok=True)
