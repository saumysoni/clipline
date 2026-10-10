"""
Stop a vlog while it's being made, and Try again after it stopped (a whole vlog; one Short's Try again is
web/try_again.py).

Stop: the route marks the job in STOPPING; the job's own thread notices at its next progress report (stop_point
raises Stopped) and cleans up itself (finish_stop), so nothing is deleted under a thread still writing to it. A vlog
already prepared for YouTube (job["vdraft"]: maybe uploaded) goes back to "ready to make Shorts"; anything else is
removed completely. The job threads end with settle(), which refuses under LOCK once a Stop was asked for, so a Stop
pressed at the last moment is never lost.

Try again: reruns the job on the video Pit Crew still has (its transcript is saved, so transcribing is skipped).
"""
import json
import shutil

from flask import jsonify

from settings import JOBS_DIR

from web.server import app
from web.store import JOBS, LOCK, load_job


STOPPING = set()  # job ids whose Stop was pressed and whose thread hasn't finished yet


class Stopped(Exception):
    """Raised inside a job's thread when the creator pressed Stop."""


def stop_point(job_id):
    if job_id in STOPPING:
        raise Stopped()


def settle(job_id, **kw):
    """A job thread's last change (ready, or stopped with an error), unless Stop was pressed: then False, and the
    thread calls finish_stop()."""
    with LOCK:
        if job_id in STOPPING:
            return False
        JOBS[job_id].update(kw)
        (JOBS_DIR / job_id / "job.json").write_text(json.dumps(JOBS[job_id], default=str), encoding="utf-8")
    return True


def finish_stop(job_id):
    """Called by the job's own thread once it has stopped."""
    from web.vlog_upload import VLOG_STAGES  # (vlog_upload imports this file)

    with LOCK:
        job = JOBS.get(job_id) or {}
        keep = bool(job.get("vdraft"))
        if keep:  # its title, description, thumbnail and YouTube upload stay
            job.update(status="ready", count=0, stages=VLOG_STAGES, stage=len(VLOG_STAGES), pct=100, msg="Ready",
                       error="", shorts=[], moments_found=[])
            (JOBS_DIR / job_id / "job.json").write_text(json.dumps(job, default=str), encoding="utf-8")
        else:
            JOBS.pop(job_id, None)
            (JOBS_DIR / job_id / "job.json").unlink(missing_ok=True)  # first, so nothing loads it again
        STOPPING.discard(job_id)
    if not keep:
        shutil.rmtree(JOBS_DIR / job_id, ignore_errors=True)
    print(f"Vlog {job_id} stopped by its creator ({'back to ready' if keep else 'removed'}).")


@app.post("/api/vlogs/<job_id>/stop")
def stop_vlog(job_id):
    from web.job_queue import take_waiting  # (the queue imports this file)

    with LOCK:
        job = load_job(job_id)
        kept = bool(job.get("vdraft"))
    if take_waiting(job_id):  # hadn't started: nothing is running, so clean up now
        finish_stop(job_id)
        return jsonify(ok=True, kept=kept)
    with LOCK:  # being made: its thread stops at its next progress report
        if job.get("status") != "working":
            return jsonify(error="This vlog isn't being made any more."), 400
        STOPPING.add(job_id)
    return jsonify(ok=True, kept=kept)


@app.post("/api/vlogs/<job_id>/again")
def vlog_again(job_id):
    from web.job_queue import enqueue_locked  # (the queue imports this file)

    with LOCK:
        job = load_job(job_id)
        if job.get("status") != "error":
            return jsonify(error="This vlog isn't stopped, so there's nothing to try again."), 400
        src = next((JOBS_DIR / job_id).glob("source.*"), None)
        if job.get("video_deleted_at") or not src:
            return jsonify(error="Pit Crew no longer has this vlog's video (it's deleted a while after it stopped, "
                                 "to keep storage free). Upload it again."), 400
        prep = job.get("kind") == "vlog" and not job.get("count")
        job.update(error_detail="", shorts=[], moments_found=[], little_speech=False, recoveries=0)
        enqueue_locked(job)  # web/job_queue.py runs it again from what's saved on the job
    return jsonify(ok=True, prep=prep)
