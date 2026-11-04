"""
A clip or video Pit Crew posted that's no longer on YouTube or Instagram (deleted there, or removed by the platform). It no longer counts as
posted: it's a grey "Removed or deleted" card on Shorts & Reels or the Videos page, with Back to Drafts and Remove.

  - A Short: job["yt_removed"] entries (web/youtube_sync.py), or status "removed" on its job["ig_posts"] entry (sync_instagram below, daily).
  - A vlog upload: vpost state "removed" (web/youtube_sync.py).

Deleting through Pit Crew itself (Shorts & Reels › ⋮ › Delete) isn't this: the creator asked for it, so it's simply a draft again.
"""
import json
import time

from flask import abort, g, jsonify, request

from instagram import http as ig_http
from instagram.config import API_VERSION, GRAPH
from instagram.connection import load as ig_load
from instagram.http import InstagramError
from settings import JOBS_DIR

from web.instagram_posting import _mutate
from web.retention import _remove, _short_files
from web.server import app
from web.store import JOBS, LOCK, load_job, update_short
from web.vlogs import user_jobs


def _save(job):
    JOBS[job["id"]] = job
    (JOBS_DIR / job["id"] / "job.json").write_text(json.dumps(job, default=str), encoding="utf-8")


def sync_instagram(user_id, now=None):
    """Once a day: each Reel Pit Crew posted that Instagram says doesn't exist (error 100) is marked removed. Any other
    answer, or an account that isn't connected, changes nothing. Returns how many."""
    n, now = 0, now or time.time()
    for job in user_jobs(user_id):
        for p in job.get("ig_posts") or []:
            if p.get("status") != "done" or not p.get("media_id"):
                continue
            info = ig_load(user_id, p.get("ig_id"))
            if not info:
                continue
            try:
                ig_http.call("GET", f"{GRAPH}/{API_VERSION}/{p['media_id']}", {"fields": "id", "access_token": info["token"]})
            except InstagramError as e:
                if e.code != 100:
                    continue
                mid = p["media_id"]
                _mutate(job["id"], lambda posts, mid=mid: [{**x, "status": "removed", "removed_at": now} if x.get("media_id") == mid else x
                                                            for x in posts])
                n += 1
            except Exception:  # noqa: BLE001  (network trouble: tomorrow)
                continue
    return n


@app.post("/api/clips/<job_id>/<int:idx>/removed")
def clip_removed_action(job_id, idx):
    """{action: "draft"}: a draft again, to edit and post again. {action: "clear"}: the card goes, and the Short with it if
    it's on neither platform any more."""
    action = (request.get_json(force=True) or {}).get("action")
    if action not in ("draft", "clear"):
        return jsonify(error="Choose Back to Drafts or Remove."), 400
    files = None
    with LOCK:
        job = load_job(job_id)
        if not job:
            abort(404)
        s = next((x for x in job.get("shorts", []) if x["idx"] == idx), None)
        was_yt = [r for r in job.get("yt_removed") or [] if r["idx"] == idx]
        was_ig = [p for p in job.get("ig_posts") or [] if p["idx"] == idx and p.get("status") == "removed"]
        if not s or not (was_yt or was_ig):
            return jsonify(error="That clip isn't marked as removed any more. Refresh the page."), 400
        if action == "draft" and s.get("file_deleted_at"):
            return jsonify(error="Pit Crew no longer keeps this clip's video, so it can't go back to Drafts. Remove the card."), 400
        job["yt_removed"] = [r for r in job.get("yt_removed") or [] if r["idx"] != idx]
        job["ig_posts"] = [p for p in job.get("ig_posts") or [] if not (p["idx"] == idx and p.get("status") == "removed")]
        still = any(u["idx"] == idx for u in job.get("uploads") or []) or any(p["idx"] == idx for p in job["ig_posts"])
        if action == "clear" and not still:
            job["shorts"] = [x for x in job["shorts"] if x["idx"] != idx]
            files = _short_files(JOBS_DIR / job_id, s)
        _save(job)
    if files:
        _remove(files)
    elif action == "draft":
        update_short(job_id, idx, back_in_drafts_at=time.time())  # its storage clocks start afresh (gotcha 21)
    return jsonify(ok=True)


@app.post("/api/vlogs/<job_id>/removed")
def vlog_removed_action(job_id):
    """{action: "draft"}: back to Drafts to upload again, while Pit Crew still has the video. {action: "clear"}: the card goes."""
    action = (request.get_json(force=True) or {}).get("action")
    if action not in ("draft", "clear"):
        return jsonify(error="Choose Back to Drafts or Remove."), 400
    with LOCK:
        job = load_job(job_id)
        if not job:
            abort(404)
        post = job.get("vpost") or {}
        if post.get("state") != "removed":
            return jsonify(error="That video isn't marked as removed any more. Refresh the page."), 400
        if action == "draft" and (job.get("video_deleted_at") or not next((JOBS_DIR / job_id).glob("source.*"), None)):
            return jsonify(error="Pit Crew no longer keeps this video's file, so it can't go back to Drafts. Upload the original file again."), 400
        job["vpost"] = None if action == "draft" else {"state": "cleared", "removed_at": post.get("removed_at")}
        if action == "draft":
            job["last_edit_at"] = time.time()  # the video is kept KEEP_ORIGINAL_HOURS from now (gotcha 21)
        _save(job)
    return jsonify(ok=True)
