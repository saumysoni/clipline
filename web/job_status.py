"""
Progress: the page asks for the job's state every second.
"""
from flask import abort, jsonify

from web.server import app
from web.store import LOCK, load_job


@app.get("/api/status/<job_id>")
def status(job_id):
    with LOCK:
        job = load_job(job_id)
        if not job:
            abort(404)
        return jsonify(job)
