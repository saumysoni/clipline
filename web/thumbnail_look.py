"""
Thumbnail look: switch one Short's thumbnail between Frame and Duotone. Redrawn from the frames and
plan saved when it was made (pipeline.relook_thumbnail): no AI, about a second, in the background.
"""
import json
import threading
import traceback

from flask import abort, jsonify, request

import pipeline
from settings import JOBS_DIR

from web.server import app
from web.store import JOBS, LOCK, RETRY_LOCKS, editable_job, next_file_number, update, update_short


def redraw_look(job_id, idx, look):
    job_dir = JOBS_DIR / job_id
    with LOCK:
        lock = RETRY_LOCKS.setdefault(job_id, threading.Lock())
    try:
        with lock:
            update_short(job_id, idx, retry_msg="Redrawing the thumbnail")
            with LOCK:
                job = json.loads(json.dumps(JOBS[job_id]))
            me = next(s for s in job["shorts"] if s["idx"] == idx)
            name, work = pipeline.relook_thumbnail(me, next_file_number(job), job_dir, look)
        update_short(job_id, idx, thumb=name, thumb_work=work, thumb_look=look, retrying=False, retry_msg=None)
    except Exception as e:
        traceback.print_exc()
        update_short(job_id, idx, retrying=False, retry_error=str(e) if isinstance(e, RuntimeError)
                     else "Couldn't redraw the thumbnail. Please try again.")


@app.post("/api/look/<job_id>/<int:idx>")
def set_look(job_id, idx):
    """Redraw this Short's thumbnail in another look (frame or duotone)."""
    look = str((request.get_json(silent=True) or {}).get("look", "")).strip().lower()
    if look not in pipeline.THUMB_LOOKS:
        return jsonify(error="Choose Frame or Duotone."), 400
    with LOCK:
        job, problem = editable_job(job_id)
        if problem:
            return problem
        me = next((s for s in job["shorts"] if s["idx"] == idx and not s.get("pending")), None)
        if not me:
            abort(404)
        if me.get("retrying"):
            return jsonify(error="This Short is still being made. Wait a moment."), 400
    if job.get("upload_status") == "error":
        update(job_id, upload_status=None)
    update_short(job_id, idx, retrying=True, retry_msg="Waiting for the other Short to finish", retry_error=None)
    threading.Thread(target=redraw_look, args=(job_id, idx, look), daemon=True).start()
    return jsonify(ok=True)
