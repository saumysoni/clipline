"""
The vlog queue: every vlog that's transcribed and edited (Make Shorts, preparing a vlog upload, its Shorts later, Try
again) waits here for a free spot, so a few creators uploading at once can't run the server out of memory.

JOB_SLOTS vlogs run at once (default 2), at most JOB_SLOTS_PER_CREATOR (default 1) from one creator, so one person's
ten vlogs don't hold everyone else up. A waiting vlog is status "working" with queued=True (Stop, the Vlogs list and
the progress card treat it like one being made) and the message "Waiting for a free spot" / "Starts after your other
vlog". Waiting order is job["queued_at"].

A waiting vlog's message says where it is and, once this server has finished a vlog, about how long until it starts:
"Next in line · about 4 min" (until it starts), "3rd in line · ...". The time is learned on this server (SPEED: seconds per
minute of video, separately for making Shorts and preparing a vlog upload, from runs that finished without a pause)
and counts the vlogs ahead (what's left of the ones running, by their progress) shared over SLOTS. With nothing
learned yet only the place is said: never a made-up time.

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

from web.priority import lower
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
LENGTHS = {}  # job id -> its video's minutes (read outside the lock: _lengths)
SPEED_FILE = "_queue_speed.json"  # in JOBS_DIR: {"shorts" | "prep": seconds per minute of video}


def _kind(job):
    return "prep" if job.get("kind") == "vlog" and not job.get("count") else "shorts"


def _speed():
    try:
        return json.loads((JOBS_DIR / SPEED_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


SPEED = _speed()


def _learn(kind, seconds, minutes):
    """A run that finished without a pause: seconds it took per minute of video, averaged with what's known."""
    if minutes < 0.5 or seconds <= 0:
        return
    rate = seconds / minutes
    with LOCK:
        SPEED[kind] = round(rate if kind not in SPEED else 0.7 * SPEED[kind] + 0.3 * rate, 1)
        try:
            (JOBS_DIR / SPEED_FILE).write_text(json.dumps(SPEED), encoding="utf-8")
        except OSError:
            pass


def _lengths():
    """The minutes of each waiting vlog's video (probe: remembered, gotcha 37d), read without the lock held."""
    from pipeline import probe
    with LOCK:
        todo = [(j, (JOBS.get(j) or {}).get("duration")) for j in WAITING + list(RUNNING) if j not in LENGTHS]
    for jid, seconds in todo:
        if not seconds:
            src = next((JOBS_DIR / jid).glob("source.*"), None)
            try:
                seconds = probe(src)["duration"] if src else None
            except Exception:  # noqa: BLE001  (no time for it, only its place)
                seconds = None
        if seconds:
            LENGTHS[jid] = seconds / 60


def _ordinal(n):
    return "Next" if n == 1 else f"{n}{'th' if 10 <= n % 100 <= 20 else {2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _when(seconds):
    m = max(1, round(seconds / 60))
    if m < 60:
        return f"about {m} min"
    h, m = divmod(m, 60)
    return f"about {h} h {m} min" if m >= 5 else f"about {h} h"


def _wait_locked(place):
    """Seconds until the vlog at this place (0 = next) starts, or None if anything ahead can't be timed."""
    total = 0.0
    for jid in list(RUNNING):
        job, minutes = JOBS.get(jid) or {}, LENGTHS.get(jid)
        rate = SPEED.get(_kind(job))
        if not minutes or not rate:
            return None
        total += minutes * rate * max(0.05, 1 - (job.get("pct") or 0) / 100)
    for jid in WAITING[:place]:
        job, minutes = JOBS.get(jid) or {}, LENGTHS.get(jid)
        rate = SPEED.get(_kind(job))
        if not minutes or not rate:
            return None
        total += minutes * rate
    return total / SLOTS


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
    """The message on each waiting vlog: its place, and when it starts once that can be told."""
    for place, jid in enumerate(WAITING):
        job = JOBS.get(jid)
        if not job:
            continue
        if _mine_running(job.get("owner")) >= PER_CREATOR:
            msg = "Starts after your other video"
        else:
            wait = _wait_locked(place)
            msg = f"{_ordinal(place + 1)} in line" + (f" · {_when(wait)}" if wait is not None else "")
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
        settle(job_id, status="error", error="Pit Crew no longer has this video's file. Upload it again.",
               last_edit_at=time.time())
        return
    if job.get("kind") == "vlog" and not job.get("count"):
        prepare_vlog(job_id, src, link)
    else:
        must = tuple((m["start"], m["end"]) for m in job.get("must") or [])
        make_shorts(job_id, src, link, job.get("count") or 5, job.get("style", "bold"), job.get("vlog"),
                    job.get("note", ""), must, game=job.get("game"))


def _run(job_id):
    lower()  # it gives way to the pages and the editor (web/priority.py)
    started = time.time()
    with LOCK:
        kind = _kind(JOBS.get(job_id) or {})
    try:
        run_job(job_id)
        with LOCK:
            job = dict(JOBS.get(job_id) or {})
        if job.get("status") == "ready" and (job.get("paused_at") or 0) < started and job.get("duration"):
            _learn(kind, time.time() - started, job["duration"] / 60)  # (a paused run's time says nothing)
    except Exception:  # noqa: BLE001  (the run records its own errors; this is only a last guard)
        traceback.print_exc()
    finally:
        with LOCK:
            RUNNING.pop(job_id, None)
            LENGTHS.pop(job_id, None)
            _paint_locked()
            QUEUE.notify_all()


def _dispatch():
    # Load every vlog once, so ones that were under way when Pit Crew stopped are queued again now.
    for path in JOBS_DIR.glob("*/job.json"):
        with LOCK:
            load_job(path.parent.name)
    while True:
        _lengths()
        with LOCK:
            jid = _next_locked()
            while jid is None:
                _paint_locked()  # (the time left changes as the running vlogs move on)
                QUEUE.wait(timeout=5)  # also wakes now and then for vlogs recovered by someone else's load
                if any(j not in LENGTHS for j in WAITING):
                    break
                jid = _next_locked()
            if jid is None:
                continue
            WAITING.remove(jid)
            job = JOBS[jid]
            RUNNING[jid] = job.get("owner")
            job.update(queued=False)
            _save(job)
            _paint_locked()
        threading.Thread(target=_run, args=(jid,), daemon=True).start()


threading.Thread(target=_dispatch, daemon=True, name="job-queue").start()  # name: /healthz looks for it
