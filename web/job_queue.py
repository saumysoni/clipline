"""
The vlog queue: every vlog that's transcribed and edited (Make Shorts, preparing a vlog upload, its Shorts later, Try
again) waits here for a free spot, so a few creators uploading at once can't run the server out of memory.

JOB_SLOTS vlogs run at once (default 2), at most JOB_SLOTS_PER_CREATOR (default 1) from one creator, so one person's
ten vlogs don't hold everyone else up. A waiting vlog is status "working" with queued=True (Stop, the Vlogs list and
the progress card treat it like one being made) and the message "Waiting for a free spot" / "Starts after your other
vlog". Waiting order is job["queued_at"].

Vlogs that were being made or waiting when Pit Crew stopped are queued again on start (web/store.py `_restarted`). One
dispatcher thread starts each run in its own thread and frees the spot whatever happens (ready, stopped, error).

Cloud: this is in memory in one process (like the Instagram scheduler). Run exactly one Pit Crew process, or move this
to a real job queue with workers; the job's own fields (status, queued, queued_at) are what such a queue would read.
"""
import json
import os
import threading
import time
import traceback

from settings import JOBS_DIR

from web.store import JOBS, LOCK, RECOVERED, WAITING_MSG, load_job


def _setting(name, default):
    try:
        return max(1, int(os.getenv(name, default)))
    except ValueError:
        return default


SLOTS = _setting("JOB_SLOTS", 2)
PER_CREATOR = _setting("JOB_SLOTS_PER_CREATOR", 1)

QUEUE = threading.Condition(LOCK)  # the same lock as every job change, so nothing can slip in between
WAITING = []  # job ids in order
RUNNING = {}  # job id -> owner


def _save(job):
    (JOBS_DIR / job["id"] / "job.json").write_text(json.dumps(job, default=str), encoding="utf-8")


def enqueue_locked(job):
    """Queue a job (call with LOCK held). The run itself is built from the job (run_job), so store everything it
    needs on the job first (count, style, vlog, note, must, link)."""
    job.update(status="working", queued=True, queued_at=time.time(), stage=0, pct=0, msg=WAITING_MSG, error="")
    if job["id"] not in WAITING:
        WAITING.append(job["id"])
    _paint_locked()
    _save(job)
    QUEUE.notify_all()


def take_waiting(job_id):
    """Stop pressed on a vlog that hasn't started: True if it was waiting (it's out of the queue now; the caller then
    calls finish_stop, outside the lock)."""
    with LOCK:
        if job_id in WAITING:
            WAITING.remove(job_id)
            _paint_locked()
            QUEUE.notify_all()
            return True
    return False


def _mine_running(owner):
    return sum(1 for o in RUNNING.values() if o == owner)


def _paint_locked():
    """The message on each waiting vlog."""
    for jid in WAITING:
        job = JOBS.get(jid)
        if not job:
            continue
        msg = "Starts after your other vlog" if _mine_running(job.get("owner")) >= PER_CREATOR else WAITING_MSG
        if job.get("msg") != msg:
            job["msg"] = msg
            _save(job)


def _next_locked():
    while RECOVERED:  # vlogs that were under way when Pit Crew stopped (loaded by whoever asked first)
        jid = RECOVERED.pop(0)
        if jid not in WAITING:
            WAITING.append(jid)
    WAITING[:] = [j for j in WAITING if j in JOBS]  # removed meanwhile (account deleted)
    WAITING.sort(key=lambda j: (JOBS.get(j) or {}).get("queued_at") or 0)
    if len(RUNNING) >= SLOTS:
        return None
    for jid in WAITING:
        job = JOBS.get(jid)
        if job and _mine_running(job.get("owner")) < PER_CREATOR:
            return jid
    return None


def run_job(job_id):
    """Run one queued vlog with what's saved on it: prepare a vlog upload, or make Shorts."""
    from web.make_shorts import make_shorts  # (both import this file)
    from web.stop_and_retry import settle
    from web.vlog_upload import prepare_vlog

    with LOCK:
        job = json.loads(json.dumps(load_job(job_id), default=str))
    src = next((JOBS_DIR / job_id).glob("source.*"), None)
    link = None if src else job.get("link")
    if not src and not link:
        settle(job_id, status="error", error="Pit Crew no longer has this vlog's video. Upload it again.",
               last_edit_at=time.time())
        return
    if job.get("kind") == "vlog" and not job.get("count"):
        prepare_vlog(job_id, src, link)
    else:
        must = tuple((m["start"], m["end"]) for m in job.get("must") or [])
        make_shorts(job_id, src, link, job.get("count") or 5, job.get("style", "bold"), job.get("vlog"),
                    job.get("note", ""), must)


def _run(job_id):
    try:
        run_job(job_id)
    except Exception:  # noqa: BLE001  (the run records its own errors; this is only a last guard)
        traceback.print_exc()
    finally:
        with LOCK:
            RUNNING.pop(job_id, None)
            _paint_locked()
            QUEUE.notify_all()


def _dispatch():
    # Load every vlog once, so ones that were under way when Pit Crew stopped are queued again now.
    for path in JOBS_DIR.glob("*/job.json"):
        with LOCK:
            load_job(path.parent.name)
    while True:
        with LOCK:
            jid = _next_locked()
            while jid is None:
                QUEUE.wait(timeout=5)  # also wakes now and then for vlogs recovered by someone else's load
                jid = _next_locked()
            WAITING.remove(jid)
            job = JOBS[jid]
            RUNNING[jid] = job.get("owner")
            job.update(queued=False)
            _save(job)
            _paint_locked()
        threading.Thread(target=_run, args=(jid,), daemon=True).start()


threading.Thread(target=_dispatch, daemon=True).start()
