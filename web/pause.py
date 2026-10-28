"""
Pause and Resume while Shorts are being made (the making page and Drafts' card for a vlog being made).

Pause takes effect after the current step, at a safe point (pause_point in web/make_shorts.py: before transcribing,
before finding moments, before each Short is edited, before each thumbnail is waited for), never half-way through one.
A vlog still waiting for a free spot pauses at once. A paused vlog leaves the queue (its spot goes to the next one),
keeps what's done (transcript, the moments chosen, Shorts edited, thumbnails made) and its status is "paused".
Resume queues it again; the run skips what's done and carries on.

Stop works on a paused vlog too (nothing is running, so it's cleaned up at once). A paused vlog's video is kept like a
stopped one's (web/retention.py), then it can't be resumed.
"""
import time

from flask import abort, g, jsonify

from web.server import app
from web.store import JOBS, LOCK, load_job, update


PAUSING = set()  # job ids whose Pause was pressed and whose run hasn't reached a safe point yet


class Paused(Exception):
    """Raised inside a run at a safe point once the creator pressed Pause."""


def pause_point(job_id):
    """A safe point in a run: pauses here if Pause was pressed."""
    if job_id in PAUSING:
        raise Paused()


def paused_now(job_id, settle):
    """The run reached a safe point after Pause (settle: web/stop_and_retry.py, refuses if Stop was pressed)."""
    now = time.time()
    with LOCK:
        PAUSING.discard(job_id)
    return settle(job_id, status="paused", pausing=False, queued=False, msg="Paused", paused_at=now, last_edit_at=now)


def _mine(job_id):
    with LOCK:
        job = load_job(job_id)
    if not job or job.get("owner") != g.user["id"]:
        abort(404)
    return job


def _makes_shorts(job):
    return not (job.get("kind") == "vlog" and not job.get("count"))  # not a vlog upload being prepared


@app.post("/api/vlogs/<job_id>/pause")
def pause_vlog(job_id):
    from web.job_queue import take_waiting  # (the queue imports make_shorts, which imports this file)
    from web.stop_and_retry import STOPPING

    job = _mine(job_id)
    if not _makes_shorts(job):
        return jsonify(error="Only making Shorts can be paused."), 400
    if job.get("status") == "paused":
        return jsonify(ok=True, paused=True)
    if job.get("status") != "working" or job_id in STOPPING:
        return jsonify(error="These Shorts aren't being made any more."), 400
    if take_waiting(job_id):  # hadn't started: paused right away
        now = time.time()
        update(job_id, status="paused", pausing=False, queued=False, msg="Paused", paused_at=now, last_edit_at=now)
        return jsonify(ok=True, paused=True)
    with LOCK:  # being made: it pauses at its next safe point
        PAUSING.add(job_id)
        if job_id in JOBS:
            JOBS[job_id]["pausing"] = True
    return jsonify(ok=True, paused=False)


@app.post("/api/vlogs/<job_id>/resume")
def resume_vlog(job_id):
    from web.job_queue import enqueue_locked

    job = _mine(job_id)
    with LOCK:
        job = load_job(job_id)
        if job.get("status") == "working" and job_id in PAUSING:  # Pause pressed, not reached yet: just carry on
            PAUSING.discard(job_id)
            job["pausing"] = False
            return jsonify(ok=True)
        if job.get("status") != "paused":
            return jsonify(error="These Shorts aren't paused."), 400
        if job.get("video_deleted_at") or not job.get("link") and not _has_video(job_id):
            return jsonify(error="Pit Crew no longer has this vlog's video (it's deleted a while after it was paused, "
                                 "to keep storage free). Upload it again."), 400
        job.update(pausing=False, recoveries=0)
        enqueue_locked(job)  # web/job_queue.py runs it again; it skips what's done
    return jsonify(ok=True)


def _has_video(job_id):
    from settings import JOBS_DIR
    return next((JOBS_DIR / job_id).glob("source.*"), None) is not None
