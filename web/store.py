"""
Jobs: their state in memory (JOBS), saved to jobs/<id>/job.json, and helpers to read and change them.
"""
import json
import re
import threading
import time

from flask import abort, jsonify

from settings import JOBS_DIR


JOBS = {}


LOCK = threading.Lock()


STAGES = ["Getting your vlog", "Transcribing", "Finding the best moments",
          "Editing Shorts", "Designing thumbnails"]


# Vlogs that were being made (or waiting) when Pit Crew stopped are picked up again on the next start
# (web/job_queue.py takes them from RECOVERED). At most MAX_RECOVERIES times for one that was running: if a vlog is what
# brings Pit Crew down, re-running it on every start would bring it down again and again.
RECOVERED = []
MAX_RECOVERIES = 2
RECOVER_WITHIN = 6 * 3600  # job.json is rewritten at every progress report: older than this = abandoned long ago, not a restart
WAITING_MSG = "Waiting for a free spot"


def _restarted(job, job_dir):
    """A job.json that says "working" from before this start: queue it again (True), or it stays stopped (False)."""
    ran = not job.get("queued")
    tries = job.get("recoveries", 0) + (1 if ran else 0)
    try:  # (one that was only waiting comes back however long it waited)
        if ran and time.time() - (job_dir / "job.json").stat().st_mtime > RECOVER_WITHIN:
            return False
    except OSError:
        return False
    if job.get("link") and not job.get("duration"):  # never read: the Google Drive download may have stopped half-way
        for f in job_dir.glob("source.*"):
            f.unlink(missing_ok=True)
    has_video = next(job_dir.glob("source.*"), None) or job.get("link")
    if not has_video or tries > MAX_RECOVERIES:
        return False
    job.update(status="working", queued=True, queued_at=job.get("queued_at") or job.get("created_at") or time.time(),
               stage=0, pct=0, msg=WAITING_MSG, recoveries=tries, error="")
    if job.get("kind") != "vlog" or job.get("count"):
        job["shorts"] = []  # a Shorts run starts over (its transcript is saved, so that part is quick)
    RECOVERED.append(job["id"])
    print(f"Vlog {job['id']} was being made when Pit Crew stopped: queued again (try {tries}).")
    return True


def update(job_id, **kw):
    with LOCK:
        JOBS[job_id].update(kw)
        (JOBS_DIR / job_id / "job.json").write_text(json.dumps(JOBS[job_id], default=str), encoding="utf-8")


def load_job(job_id):
    """The job from memory, or from its job.json if the app was restarted. Call with LOCK held."""
    job = JOBS.get(job_id)
    if not job and re.fullmatch(r"[0-9a-f]{10}", job_id):
        saved = JOBS_DIR / job_id / "job.json"
        if saved.exists():  # app was restarted: reload finished jobs
            raw = saved.read_text(encoding="utf-8")
            job = json.loads(raw)
            if job.get("status") == "working" and not _restarted(job, saved.parent):
                job.update(status="error", error="Pit Crew was restarted while this was being made, so it stopped. "
                                         "Press Try again.", last_edit_at=time.time())  # kept for Try again
            if (job.get("vpost") or {}).get("state") == "uploading":  # a whole vlog going to YouTube (web/vlog_upload.py)
                job["vpost"] = {**job["vpost"], "state": "error",
                                "error": "Pit Crew was restarted while this was uploading. Check YouTube Studio; if it isn't there, press Upload again."}
            if job.get("upload_status") in ("starting", "connecting", "uploading"):
                job.update(upload_status="error", upload_msg="Pit Crew was restarted during posting. Check YouTube Studio, "
                                                         "then post the rest again.")
            job["shorts"] = [s for s in job.get("shorts", []) if not s.get("pending")]
            by_idx = {s["idx"]: s for s in job["shorts"]}
            for u in job.get("uploads") or []:  # uploads from before Pit Crew noted which file went up
                if "video" not in u and u["idx"] in by_idx:
                    u["video"], u["thumb"] = by_idx[u["idx"]]["video"], by_idx[u["idx"]]["thumb"]
            for s in job["shorts"]:
                if s.pop("retrying", None):
                    s["retry_error"] = "Pit Crew was restarted while this was being remade. Try again."
            JOBS[job_id] = job
            if json.dumps(job, default=str) != json.dumps(json.loads(raw), default=str):
                saved.write_text(json.dumps(job, default=str), encoding="utf-8")  # so the next start doesn't redo it
    return job


RETRY_LOCKS = {}  # one remake at a time per job, so two new picks can't land on the same moment


def update_short(job_id, idx, **kw):
    """Change one Short. Every change counts as an edit: it restarts the clocks for keeping the vlog's video and
    this draft (web/retention.py)."""
    with LOCK:
        job = JOBS[job_id]
        now = time.time()
        job["last_edit_at"] = now
        job["shorts"] = [{**s, **kw, "edited_at": now} if s["idx"] == idx else s for s in job["shorts"]]
        (JOBS_DIR / job_id / "job.json").write_text(json.dumps(job, default=str), encoding="utf-8")


def next_file_number(job):
    """A file number no Short uses yet, so the browser shows a new file instead of a cached old one."""
    used = [int(n) for s in job["shorts"] for n in re.findall(r"_(\d+)\.", s["video"] + s["thumb"])]
    return max(used + [len(job["shorts"])]) + 1


def editable_job(job_id):
    """The job if Shorts can be remade or added now, else an error response. Call with LOCK held."""
    job = load_job(job_id)
    if not job or job.get("status") != "ready":
        abort(400)
    if job.get("upload_status") in ("starting", "connecting", "uploading"):
        return None, (jsonify(error="Wait until posting has finished."), 400)
    return job, None
