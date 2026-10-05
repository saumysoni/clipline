"""
The Vlogs page and the sidebar's progress card: every vlog this creator has uploaded, newest first, with its
state (being made / ready / stopped), how many Shorts it has and where they are. Also deleting a vlog's video
(the Shorts, thumbnails, transcript and posts stay).
"""
import json
import re
import threading
import time
import traceback
from datetime import datetime, timezone

from flask import abort, g, jsonify, request

import pipeline
from pipeline.transcript_cache import remember_transcript
from settings import JOBS_DIR

from web.preview import PREVIEWS, PREVIEW_PCT
from web.server import app
from web.store import JOBS, LOCK, load_job, update


def created_at(job):
    """When the vlog was uploaded (seconds). Vlogs from before this was saved: when its files were written."""
    if job.get("created_at"):
        return job["created_at"]
    job_dir = JOBS_DIR / job["id"]
    for pattern in ("source.*", "transcript.json", "job.json"):
        f = next(job_dir.glob(pattern), None)
        try:
            if f:
                return f.stat().st_mtime
        except OSError:  # gone in the meantime
            continue
    return 0


def summary(job):
    """What a vlog card and the progress card show."""
    now = datetime.now(timezone.utc)
    shorts = [s for s in job.get("shorts", []) if not s.get("pending")]
    uploads = {u["idx"]: u for u in job.get("uploads") or []}
    reels = {p["idx"]: p for p in job.get("ig_posts") or []}
    posted = scheduled = drafts = 0
    for s in shorts:
        times = []
        if s["idx"] in uploads:
            when = uploads[s["idx"]].get("when")
            times.append(datetime.fromisoformat(when) if when else None)
        p = reels.get(s["idx"])
        if p and p["status"] in ("waiting", "posting", "done", "check"):
            times.append(None if p["status"] == "done" or not p.get("when") else datetime.fromisoformat(p["when"]))
        if not times:
            drafts += 1
        elif any(t is None or t <= now for t in times):
            posted += 1
        else:
            scheduled += 1
    cover = next((s["thumb"] for s in shorts if s.get("thumb")), "")
    vid = re.search(r"(?:v=|youtu\.be/|/shorts/|/live/)([\w-]{11})", (job.get("vlog") or {}).get("youtube_url") or "")
    vlog = job.get("vlog") or {}
    return {"id": job["id"], "title": vlog.get("title") or job.get("name") or "Your vlog",
            "duration": job.get("duration"), "created": created_at(job), "status": job.get("status"),
            "stage": job.get("stage", 0), "stages": len(job.get("stages") or []), "pct": job.get("pct"),
            "msg": job.get("msg", ""), "error": job.get("error", ""), "cover": cover, "poster": _poster(job),
            "yt_thumb": f"https://i.ytimg.com/vi/{vid.group(1)}/mqdefault.jpg" if vid else "",
            "shorts": len(shorts), "posted": posted, "scheduled": scheduled, "drafts": drafts,
            "remaking": any(s.get("retrying") for s in job.get("shorts", [])),
            "youtube_url": vlog.get("youtube_url", ""), "video_deleted": bool(job.get("video_deleted_at")),
            "video_expires": _video_expires(job)}


POSTERING = set()  # vlogs whose poster is being made right now


def _poster(job):
    """The vlog's landscape poster (pipeline/poster.py) if it exists. Made once in the background, the first time the
    list is shown while the vlog's video is still here; until then the list shows a Short's thumbnail."""
    job_dir = JOBS_DIR / job["id"]
    if (job_dir / "poster.jpg").exists():
        return "poster.jpg"
    if job.get("status") == "ready" and not job.get("video_deleted_at") and job["id"] not in POSTERING:
        src = next(job_dir.glob("source.*"), None)
        if src:
            POSTERING.add(job["id"])
            threading.Thread(target=_make_poster, args=(job["id"], src, job.get("duration")), daemon=True).start()
    return ""


def _make_poster(job_id, src, duration):
    try:
        pipeline.make_poster(src, JOBS_DIR / job_id / "poster.jpg", duration)
    except Exception:  # noqa: BLE001  (the list just keeps showing a Short's thumbnail)
        traceback.print_exc()
    finally:
        POSTERING.discard(job_id)


def _video_expires(job):
    from web.retention import video_expires  # (retention imports this file)
    return video_expires(job) if job.get("status") == "ready" else None


def user_jobs(user_id):
    """Every job this user owns (from memory, or job.json after a restart)."""
    with LOCK:
        ids = {p.parent.name for p in JOBS_DIR.glob("*/job.json")} | set(JOBS)
        jobs = [load_job(i) for i in ids if re.fullmatch(r"[0-9a-f]{10}", i)]
        return [json.loads(json.dumps(j, default=str)) for j in jobs if j and j.get("owner") == user_id]


@app.get("/api/vlogs")
def vlogs():
    items = sorted((summary(j) for j in user_jobs(g.user["id"])), key=lambda v: v["created"], reverse=True)
    return jsonify(items=items)


def _cant_delete(job):
    """Why this vlog's video can't be deleted right now, or None."""
    if job.get("status") == "working":
        return "Pit Crew is still making Shorts from this vlog. Wait until they're ready."
    if any(s.get("retrying") for s in job.get("shorts", [])):
        return "A Short from this vlog is being remade. Wait until it's ready."
    if job.get("upload_status") in ("starting", "connecting", "uploading"):
        return "Wait until posting has finished."
    return None


@app.post("/api/vlogs/<job_id>/delete-video")
def delete_video(job_id):
    """Delete the vlog's video (and the small copy for choosing scenes). Everything made from it stays: Shorts,
    thumbnails, transcript, posts. Making new Shorts from it then needs the vlog uploaded again (its transcript is
    remembered, so that skips transcribing)."""
    with LOCK:
        job = load_job(job_id)
        if not job:
            abort(404)
        why = _cant_delete(job)
    if why:
        return jsonify(error=why), 400
    remove_video(job_id)
    return jsonify(ok=True)


@app.post("/api/vlogs/delete-videos")
def delete_videos():
    """Several at once (Select all on the Vlogs page). Only this creator's vlogs; busy ones are skipped and listed."""
    ids = [i for i in (request.get_json(force=True).get("ids") or []) if isinstance(i, str) and re.fullmatch(r"[0-9a-f]{10}", i)]
    deleted, skipped = [], []
    for job_id in dict.fromkeys(ids):
        with LOCK:
            job = load_job(job_id)
            if not job or job.get("owner") != g.user["id"]:
                continue
            why = None if not job.get("video_deleted_at") else "already deleted"
            why = why or _cant_delete(job)
        if why:
            skipped.append(job_id)
            continue
        remove_video(job_id)
        deleted.append(job_id)
    return jsonify(ok=True, deleted=deleted, skipped=skipped)


def remove_video(job_id):
    """Delete a vlog's video and the small copy for choosing scenes (by the creator, or by web/retention.py).
    Its transcript is remembered first, so uploading the same vlog again skips transcribing."""
    job_dir = JOBS_DIR / job_id
    with LOCK:
        job = load_job(job_id)
        src = next(job_dir.glob("source.*"), None)
        uploaded = created_at(job)  # older vlogs date from their video file: keep that date before it goes
        PREVIEWS.pop(job_id, None)
        PREVIEW_PCT.pop(job_id, None)
    if src:
        remember_transcript(src, job_dir / "transcript.json")
    for f in (src, job_dir / "preview.mp4", job_dir / "preview.part.mp4"):
        if f:
            f.unlink(missing_ok=True)
    update(job_id, video_deleted_at=time.time(), created_at=uploaded)
