"""
Add a Short: a moment the AI missed, described in words or given as times.
"""
import json
import threading

from flask import jsonify, request

from settings import JOBS_DIR

from web.server import app
from web.store import LOCK, editable_job
from web.times import read_times
from web.try_again import remake_short


@app.post("/api/add/<job_id>")
def add_short(job_id):
    """A Short for a moment the AI missed: described in words, or the creator's own times."""
    data = request.get_json(silent=True) or {}
    note = str(data.get("note", ""))[:500]
    try:
        times = read_times(data.get("start"), data.get("end"))
    except RuntimeError as e:
        return jsonify(error=str(e)), 400
    if not times and not note.strip():
        return jsonify(error="Describe the moment you want, or type its From and To times."), 400
    with LOCK:
        job, problem = editable_job(job_id)
        if problem:
            return problem
        if len(job["shorts"]) >= 20:
            return jsonify(error="That's the most Shorts one vlog can have here (20)."), 400
        idx = max([s["idx"] for s in job["shorts"]] + [0]) + 1
        job["shorts"].append({"idx": idx, "pending": True, "retrying": True, "retry_msg": "Waiting for the other Short to finish",
                              "start": 0, "end": 0, "title": "", "why": "", "video": "", "thumb": "", "keep": True})
        job["add_error"] = None
        if job.get("upload_status") == "error":
            job["upload_status"] = None
        (JOBS_DIR / job_id / "job.json").write_text(json.dumps(job, default=str), encoding="utf-8")
    threading.Thread(target=remake_short, args=(job_id, idx, note, times), daemon=True).start()
    return jsonify(ok=True, idx=idx)
