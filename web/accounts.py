"""
Pit Crew accounts: email + password or Continue with Google, and gate() which requires sign-in
for every /api and /media address and checks that a job belongs to the signed-in user.
"""
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


def login_problem_page(msg, email=""):
    """Back to the sign-in screen, which shows msg in red (Google sign-in happens away from the page)."""
    session["auth_error"] = {"error": msg, "email": email}
    return redirect("/")


# Anyone can make an account: email + password, or Sign in with Google (name and email only).
# Every /api and /media address needs a signed-in user, and a job is only reachable by its owner.
PUBLIC = {"index", "static", "config", "me", "auth_signup", "auth_login", "auth_logout", "auth_google",
          "auth_forgot", "auth_reset",
          "youtube_callback", "instagram_callback",  # instagram_callback: its one-time state names the user
          "instagram_video"}  # a signed, expiring link to one Reel's video, for Instagram to download


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


EMAIL_EXISTS = ("Email already exists. This email has a Pit Crew account with a password: sign in with your email "
                "and password, or use Forgot password.")


def google_user(info):
    """The Pit Crew user for a Google sign-in: found by Google account, or new. An email that already has a
    password account is refused (no automatic joining): that person signs in with their password."""
    user = db.user_by_google(info["sub"])
    if user:
        return user
    if db.user_by_email(info["email"]):
        raise RuntimeError(EMAIL_EXISTS)
    try:
        uid = db.create_user(info["email"], info["name"], google_sub=info["sub"], email_verified=info["email_verified"])
    except sqlite3.IntegrityError:  # signed up a moment ago in another tab
        user = db.user_by_email(info["email"])
        if not user or user["google_sub"] != info["sub"]:
            raise RuntimeError(EMAIL_EXISTS)
        return user
    claim_old_jobs(uid)
    return db.user_by_id(uid)


@app.get("/api/me")
def me():
    u = g.user
    problem = session.pop("auth_error", None) if not u else None  # from a Google sign-in that didn't work
    return jsonify(user={"email": u["email"], "name": u["name"]} if u else None, google=yt.is_configured(),
                   auth_error=problem)


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
