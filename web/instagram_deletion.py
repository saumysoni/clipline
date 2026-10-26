"""
Meta's two callbacks for apps that use Instagram login (Meta app → Instagram → API setup with Instagram login →
Business login settings), which Meta's App Review checks:

  - Deauthorize callback URL: https://<domain>/api/instagram/deauthorize. Meta calls it when someone removes Pit Crew in
    Instagram (Settings › Website permissions › Apps and websites): that account's connection (its token) is deleted,
    in every Pit Crew account that had connected it, as Disconnect does.
  - Data deletion request URL: https://<domain>/api/instagram/data-deletion. Meta calls it when someone asks Meta to have
    Pit Crew delete their data. As above, plus everything Pit Crew kept from Instagram about that account: the records
    of its Reels (Instagram ID, link, username; the clips themselves stay in Pit Crew, as drafts on the Instagram side)
    and their saved daily numbers. Reels still waiting to go to that account are dropped too. Pit Crew answers with a
    confirmation code and a page where the person can check it: /data-deletion?code=<code>.

Both come as a POST with a signed_request, signed with INSTAGRAM_APP_SECRET; anything not signed by it is refused.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets

from flask import abort, jsonify, request

import instagram as ig
from accounts import db
from settings import JOBS_DIR

from web.server import app
from web.store import JOBS, LOCK, load_job
from web.vlogs import user_jobs


def _b64(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def parse_signed_request(signed, secret):
    """The signed_request's data, or None if it isn't signed with this app's secret."""
    try:
        sig, payload = signed.split(".", 1)
        data = json.loads(_b64(payload))
        good = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
    except (ValueError, AttributeError, TypeError):
        return None
    if not secret or not hmac.compare_digest(_b64(sig), good) or str(data.get("algorithm", "")).upper() != "HMAC-SHA256":
        return None
    return data


def _account_id():
    from instagram.config import app_secret
    data = parse_signed_request(request.form.get("signed_request", ""), app_secret())
    if not data or not str(data.get("user_id") or "").strip():
        abort(400)
    return str(data["user_id"]).strip()


def forget_account(ig_id, everything):
    """Drop every connection to this Instagram account; with `everything`, also what Pit Crew kept about it."""
    rows = db.connections_of_account("instagram", ig_id)
    users = {r["user_id"] for r in rows}
    for r in rows:
        db.drop_connection(r["id"])
    if not everything:
        return
    media = {}
    for uid in users:
        for snap in user_jobs(uid):
            if not any(str(p.get("ig_id")) == ig_id for p in snap.get("ig_posts") or []):
                continue
            with LOCK:
                job = load_job(snap["id"])
                posts = job.get("ig_posts") or []
                gone = [p for p in posts if str(p.get("ig_id")) == ig_id and p.get("status") != "posting"]
                media.setdefault(uid, []).extend(p["media_id"] for p in gone if p.get("media_id"))
                job["ig_posts"] = [p for p in posts if p not in gone]
                JOBS[job["id"]] = job
                (JOBS_DIR / job["id"] / "job.json").write_text(json.dumps(job, default=str), encoding="utf-8")
        ig.forget_numbers(uid, media.get(uid, []))
        db.drop_reel_snapshots(media.get(uid, []))


@app.post("/api/instagram/deauthorize")
def instagram_deauthorize():
    ig_id = _account_id()
    forget_account(ig_id, everything=False)
    print(f"Instagram: account {ig_id} removed Pit Crew in Instagram; its connection was deleted.")
    return jsonify(ok=True)


@app.post("/api/instagram/data-deletion")
def instagram_data_deletion():
    ig_id = _account_id()
    forget_account(ig_id, everything=True)
    code = secrets.token_hex(8)
    db.save_deletion_request(code, "instagram")
    print(f"Instagram: data deletion asked through Meta for account {ig_id}: done, code {code}.")
    base = (os.getenv("APP_URL") or request.host_url).rstrip("/")
    return jsonify(url=f"{base}/data-deletion?code={code}", confirmation_code=code)


def deletion_status(code):
    """For /data-deletion?code=...: a line saying the request was done, or None."""
    if not re.fullmatch(r"[0-9a-f]{16}", code or ""):
        return None
    return db.deletion_request(code)
