"""
Jobs: their state in memory (JOBS), saved to jobs/<id>/job.json, and helpers to read and change them.
"""
import json
import re
import threading

from flask import abort, jsonify

from settings import JOBS_DIR


JOBS = {}


LOCK = threading.Lock()


STAGES = ["Getting your vlog", "Transcribing", "Finding the best moments",
          "Editing Shorts", "Designing thumbnails"]


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
            job = json.loads(saved.read_text(encoding="utf-8"))
            if job.get("status") == "working":
                job.update(status="error", error="Pit Crew was closed while this was running. Start it again.")
            if job.get("upload_status") in ("starting", "connecting", "uploading"):
                job.update(upload_status="error", upload_msg="Pit Crew was closed during posting.")
            job["shorts"] = [s for s in job.get("shorts", []) if not s.get("pending")]
            by_idx = {s["idx"]: s for s in job["shorts"]}
            for u in job.get("uploads") or []:  # uploads from before Pit Crew noted which file went up
                if "video" not in u and u["idx"] in by_idx:
                    u["video"], u["thumb"] = by_idx[u["idx"]]["video"], by_idx[u["idx"]]["thumb"]
            for s in job["shorts"]:
                if s.pop("retrying", None):
                    s["retry_error"] = "Pit Crew was closed while this was being remade. Try again."
            JOBS[job_id] = job
    return job


RETRY_LOCKS = {}  # one remake at a time per job, so two new picks can't land on the same moment


def update_short(job_id, idx, **kw):
    with LOCK:
        job = JOBS[job_id]
        job["shorts"] = [{**s, **kw} if s["idx"] == idx else s for s in job["shorts"]]
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
