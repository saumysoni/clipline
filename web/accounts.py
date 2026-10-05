"""
Pit Crew accounts: email + password or Continue with Google, and gate() which requires sign-in
for every /api and /media address and checks that a job belongs to the signed-in user.
"""
import html
import json
import re
import sqlite3
import time
import urllib.parse

from flask import abort, g, jsonify, redirect, request, session
from werkzeug.security import check_password_hash, generate_password_hash

import youtube as yt
from accounts import db
from settings import JOBS_DIR

from web.google_redirect import youtube_redirect_uri
from web.server import app
from web.store import JOBS, LOCK, load_job


@app.get("/api/auth/google")
def auth_google():
    """Sign in to Pit Crew with Google (the whole page goes to Google and comes back)."""
    try:
        url, session["google"] = yt.start_google("login", youtube_redirect_uri())
        return redirect(url)
    except RuntimeError as e:
        return login_problem_page(str(e))


def login_problem_page(msg):
    return (f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Pit Crew · Sign in</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{{font:16px/1.5 system-ui,sans-serif;margin:0;min-height:100vh;display:grid;place-items:center;
background:#0e1018;color:#e8eaf2;padding:16px}}main{{max-width:420px;text-align:center}}a{{color:#8fb4ff}}</style>
</head><body><main><h1 style="font-size:1.3rem">Not signed in</h1><p>{html.escape(msg)}</p>
<p><a href="/">Back to Pit Crew</a></p></main></body></html>""", 400)


# Anyone can make an account: email + password, or Sign in with Google (name and email only).
# Every /api and /media address needs a signed-in user, and a job is only reachable by its owner.
PUBLIC = {"index", "static", "config", "me", "auth_signup", "auth_login", "auth_logout", "auth_google",
          "youtube_callback", "instagram_callback"}  # instagram_callback: its one-time state names the user


EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


FAILS = {}  # (email, ip) -> times of recent wrong passwords


def current_user():
    uid = session.get("uid")
    user = db.user_by_id(uid) if uid else None
    if not user or session.get("sv") != user["session_version"]:  # signed out everywhere (e.g. Google took over)
        return None
    return user


def start_session(user):
    session.clear()
    session.permanent = True
    session.update(uid=user["id"], sv=user["session_version"])


@app.before_request
def gate():
    origin = request.headers.get("Origin")
    if request.method == "POST" and origin and \
            urllib.parse.urlparse(origin).netloc != urllib.parse.urlparse(request.host_url).netloc:
        return jsonify(error="That request came from another website, so Pit Crew ignored it."), 403
    g.user = current_user()
    if request.endpoint in PUBLIC or request.endpoint is None:
        return None
    if not g.user:
        return jsonify(error="Sign in to Pit Crew first.", login=True), 401
    job_id = (request.view_args or {}).get("job_id")
    if job_id is not None:
        with LOCK:
            job = load_job(job_id)
        if not job or job.get("owner") != g.user["id"]:
            abort(404)
    return None


def claim_old_jobs(user_id):
    """Jobs made before Pit Crew had accounts belong to the first account (the person who ran it)."""
    if db.count_users() != 1:
        return
    for path in JOBS_DIR.glob("*/job.json"):
        with LOCK:
            job = JOBS.get(path.parent.name) or json.loads(path.read_text(encoding="utf-8"))
            if job.get("owner"):
                continue
            job["owner"] = user_id
            path.write_text(json.dumps(job, default=str), encoding="utf-8")
            if path.parent.name in JOBS:
                JOBS[path.parent.name]["owner"] = user_id
        print(f"Gave job {path.parent.name} (made before accounts) to the first account.")


def google_user(info):
    """The Pit Crew user for a Google sign-in: found by Google account, linked by email, or new."""
    user = db.user_by_google(info["sub"])
    if user:
        return user
    user = db.user_by_email(info["email"])
    if user:
        if not info["email_verified"]:
            raise RuntimeError("Google hasn't confirmed this email address, so it can't be joined to your Pit Crew "
                               "account. Sign in with your email and password instead.")
        # Google proves who owns the email; a password set earlier was never checked, so it's removed.
        db.link_google(user["id"], info["sub"], info["name"], clear_password=not user["email_verified"])
        return db.user_by_id(user["id"])
    try:
        uid = db.create_user(info["email"], info["name"], google_sub=info["sub"], email_verified=info["email_verified"])
    except sqlite3.IntegrityError:  # signed up a moment ago in another tab
        return db.user_by_email(info["email"])
    claim_old_jobs(uid)
    return db.user_by_id(uid)


@app.get("/api/me")
def me():
    u = g.user
    return jsonify(user={"email": u["email"], "name": u["name"]} if u else None, google=yt.is_configured())


@app.post("/api/auth/signup")
def auth_signup():
    data = request.get_json(force=True)
    email, password = str(data.get("email", "")).strip().lower(), str(data.get("password", ""))
    if not EMAIL_RE.fullmatch(email) or len(email) > 200:
        return jsonify(error="Type a valid email address.", field="email"), 400
    if len(password) < 8:
        return jsonify(error="Choose a password with at least 8 characters.", field="password"), 400
    if len(password) > 200:
        return jsonify(error="That password is too long.", field="password"), 400
    existing = db.user_by_email(email)
    if existing:
        msg = ("This email already has a Pit Crew account through Google. Use Sign in with Google."
               if existing["google_sub"] and not existing["password_hash"]
               else "There's already an account with this email. Sign in instead.")
        return jsonify(error=msg, field="email"), 400
    try:
        uid = db.create_user(email, str(data.get("name", "")), password_hash=generate_password_hash(password))
    except sqlite3.IntegrityError:
        return jsonify(error="There's already an account with this email. Sign in instead.", field="email"), 400
    claim_old_jobs(uid)
    start_session(db.user_by_id(uid))
    return jsonify(ok=True)


@app.post("/api/auth/login")
def auth_login():
    data = request.get_json(force=True)
    email, password = str(data.get("email", "")).strip().lower(), str(data.get("password", ""))
    key, now = (email, request.remote_addr), time.time()
    recent = [t for t in FAILS.get(key, []) if now - t < 900]
    if len(recent) >= 10:
        return jsonify(error="Too many wrong tries. Wait 15 minutes, then try again."), 429
    user = db.user_by_email(email)
    if not user or not user["password_hash"] or not check_password_hash(user["password_hash"], password):
        FAILS[key] = recent + [now]
        return jsonify(error="Wrong email or password. If you made your account with Google, "
                             "use Sign in with Google."), 400
    FAILS.pop(key, None)
    start_session(user)
    return jsonify(ok=True)


@app.post("/api/auth/logout")
def auth_logout():
    session.clear()
    return jsonify(ok=True)
