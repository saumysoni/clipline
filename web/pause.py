"""
Pause and Resume while Shorts are being made (the making page and Drafts' card for a vlog being made) or a vlog upload is
being prepared (web/vlog_upload.py, its safe points are between its stages).

Pause takes effect at once, whatever the run is doing (Run below): the run's own thread only waits on helper threads
(Run.doing), so it can leave straight away. What the helper was doing stops as soon as it can: FFmpeg is killed within
0.2 s (pipeline.ffmpeg.watching), transcription at its next batch of words, keeping the words so far; an AI answer on its
way is dropped. A paused vlog leaves the queue (its spot goes to the next one), keeps what's done (the words heard so
far, the moments chosen, Shorts edited, thumbnails made) and its status is "paused". Resume queues it again and the run
carries on: transcription from the last word heard; a Short that was half edited, from that Short's start.

Stop works on a paused vlog too (nothing is running, so it's cleaned up at once). A paused vlog's video is kept like a
stopped one's (web/retention.py), then it can't be resumed.
"""
import threading
import time

from flask import abort, g, jsonify

from pipeline.ffmpeg import watching
from web.server import app
from web.stop_and_retry import Stopped, stop_point
from web.store import JOBS, LOCK, load_job, update


PAUSING = set()  # job ids whose Pause was pressed and whose run hasn't left yet
SETTLE_WAIT = 2.0  # seconds the Pause button's request waits to answer "paused"


class Paused(Exception):
    """Raised inside a run at a safe point once the creator pressed Pause."""


class Run:
    """One run of a vlog. check() is where Stop and Pause take effect; once this run has been left, a helper still
    finishing gets Paused from it too, so it can never write over the paused job or start more work."""

    def __init__(self, job_id):
        self.job_id = job_id
        self.left = threading.Event()
        self.helper = None

    def check(self):
        if self.left.is_set():
            raise Paused()
        try:
            stop_point(self.job_id)
        except Stopped:
            self.left.set()
            raise
        if self.job_id in PAUSING:
            self.left.set()
            raise Paused()

    def doing(self, fn, *args, **kw):
        """fn(...) in a helper thread, with its FFmpeg runs watched, while this thread keeps checking: Stop and Pause
        don't wait for it. Its answer is dropped then."""
        box = {}

        def work():
            with watching(check=self.check):
                try:
                    box["value"] = fn(*args, **kw)
                except BaseException as e:  # noqa: BLE001  (handed to the run below)
                    box["error"] = e

        self.helper = threading.Thread(target=work, daemon=True)
        self.helper.start()
        while self.helper.is_alive():
            self.helper.join(0.1)
            self.check()
        self.check()  # (it may have swallowed a Pause on its way out)
        if "error" in box:
            raise box["error"]
        return box.get("value")

    def wait_for_helper(self, seconds=5):
        """Before a Stop deletes the folder the helper may be writing in."""
        if self.helper:
            self.helper.join(seconds)


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


@app.post("/api/vlogs/<job_id>/pause")
def pause_vlog(job_id):
    from web.job_queue import take_waiting  # (the queue imports make_shorts, which imports this file)
    from web.stop_and_retry import STOPPING

    job = _mine(job_id)
    if job.get("status") == "paused":
        return jsonify(ok=True, paused=True)
    if job.get("status") != "working" or job_id in STOPPING:
        return jsonify(error="This isn't being made any more."), 400
    if take_waiting(job_id):  # hadn't started: paused right away
        now = time.time()
        update(job_id, status="paused", pausing=False, queued=False, msg="Paused", paused_at=now, last_edit_at=now)
        return jsonify(ok=True, paused=True)
    with LOCK:  # being made: its run leaves within a moment (Run.check)
        PAUSING.add(job_id)
        if job_id in JOBS:
            JOBS[job_id]["pausing"] = True
    end = time.time() + SETTLE_WAIT
    while time.time() < end:
        with LOCK:
            if (JOBS.get(job_id) or {}).get("status") != "working":
                break
        time.sleep(0.05)
    with LOCK:
        paused = (JOBS.get(job_id) or {}).get("status") == "paused"
    return jsonify(ok=True, paused=paused)


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
            return jsonify(error="This isn't paused."), 400
        if job.get("video_deleted_at") or not job.get("link") and not _has_video(job_id):
            return jsonify(error="Pit Crew no longer has this video's file (it's deleted a while after it was paused, "
                                 "to keep storage free). Upload it again."), 400
        job.update(pausing=False, recoveries=0)
        enqueue_locked(job)  # web/job_queue.py runs it again; it skips what's done
    return jsonify(ok=True)


def _has_video(job_id):
    from settings import JOBS_DIR
    return next((JOBS_DIR / job_id).glob("source.*"), None) is not None
