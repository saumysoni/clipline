"""
Progress: the page asks for the job's state every second.
"""
import time

from flask import abort, jsonify

from web.errors import plain_error
from web.notices import WATCHING
from web.server import app
from web.stop_and_retry import STOPPING
from web.store import LOCK, load_job


@app.get("/api/status/<job_id>")
def status(job_id):
    with LOCK:
        job = load_job(job_id)
        if not job or job_id in STOPPING:
            abort(404)
        WATCHING[job_id] = time.time()  # watching it now: no email when it finishes (web/notices.py)
        if job.get("status") == "error":  # vlogs that stopped before web/errors.py kept their raw text
            stages = job.get("stages") or []
            doing = stages[min(job.get("stage", 0), len(stages) - 1)] if stages else ""
            return jsonify({**job, "error": plain_error(job.get("error"), doing)})
        return jsonify(job)
