"""
Taking a posted clip down (Shorts & Reels › ⋮ › Delete, js/clip-remove.js).

YouTube: Pit Crew deletes the Short itself (the `youtube` scope allows it; Replace uses the same call), on the channel
it went to, then forgets the upload record. Already gone from YouTube = just forgotten.

Instagram: apps connected with Instagram Login can't delete media (Meta only allows it through Facebook Login), so the
creator deletes the Reel in Instagram and Pit Crew then checks it's gone: reading it answers error 100 ("does not
exist"). Only then is the Reel forgotten. A clip on neither platform any more is a draft again (Drafts).
"""
import json
import traceback

from flask import abort, g, jsonify

import youtube as yt
from instagram.config import API_VERSION, GRAPH
from instagram.connection import load as ig_load
from instagram import http as ig_http
from instagram.http import InstagramError
from settings import JOBS_DIR
from web.instagram_posting import _mutate
from web.posting import POSTING
from web.server import app
from web.store import JOBS, LOCK, load_job


def _record(job_id, idx, key, match):
    """This Short's record in job[key] that match() accepts, or None. Call with LOCK held."""
    job = load_job(job_id)
    if not job:
        abort(404)
    return next((r for r in job.get(key) or [] if r["idx"] == idx and match(r)), None)


@app.post("/api/clips/<job_id>/<int:idx>/delete-youtube")
def clip_delete_youtube(job_id, idx):
    with LOCK:
        if job_id in POSTING:
            return jsonify(error="This vlog's Shorts are being posted right now. Try again when that's finished."), 400
        rec = _record(job_id, idx, "uploads", lambda u: u.get("video_id"))
    if not rec:
        return jsonify(error="This Short isn't on YouTube."), 400
    vid = rec["video_id"]
    try:
        service = yt.get_service(g.user["id"], rec.get("channel"))  # the channel it went to, not the active one
        if yt.video_states(service, [vid]):  # not there any more (deleted in Studio): nothing to delete
            yt.delete_video(service, vid)
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        return jsonify(error=yt.upload_error_message(e)), 400
    with LOCK:
        job = load_job(job_id)
        job["uploads"] = [u for u in job.get("uploads") or [] if not (u["idx"] == idx and u.get("video_id") == vid)]
        JOBS[job_id] = job
        (JOBS_DIR / job_id / "job.json").write_text(json.dumps(job, default=str), encoding="utf-8")
    return jsonify(ok=True)


@app.post("/api/clips/<job_id>/<int:idx>/instagram-gone")
def clip_instagram_gone(job_id, idx):
    """{gone: true} once the creator has deleted the Reel in Instagram (then it's forgotten), else {gone: false}."""
    with LOCK:
        p = _record(job_id, idx, "ig_posts", lambda p: p.get("status") == "done" and p.get("media_id"))
    if not p:
        return jsonify(error="This Reel isn't on Instagram."), 400
    info = ig_load(g.user["id"], p.get("ig_id"))
    if not info:
        return jsonify(error=f"Connect @{p.get('username') or 'that account'} on Instagram again (Channels), so Pit "
                             "Crew can check the Reel is gone."), 400
    try:
        ig_http.call("GET", f"{GRAPH}/{API_VERSION}/{p['media_id']}", {"fields": "id", "access_token": info["token"]})
        return jsonify(gone=False)
    except InstagramError as e:
        if e.code != 100:  # 100: the Reel doesn't exist; anything else is a real problem
            return jsonify(error=str(e)), 400
    _mutate(job_id, lambda posts: [x for x in posts if not (x["idx"] == idx and x.get("media_id") == p["media_id"])])
    return jsonify(gone=True)
