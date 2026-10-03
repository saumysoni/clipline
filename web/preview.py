"""
Choosing a scene on the video: makes preview.mp4 in the background when it's needed.
"""
import threading
import traceback

from flask import abort, jsonify, request

import pipeline
from settings import JOBS_DIR

from web.server import app
from web.store import LOCK, load_job


PREVIEWS = {}  # job id -> "building" or an error message, while or after making preview.mp4


def build_preview(job_id):
    job_dir = JOBS_DIR / job_id
    try:
        src = next(job_dir.glob("source.*"), None)
        if not src:
            raise RuntimeError("The original video for this job is gone, so it can't be shown. "
                               "Start a new vlog instead.")
        pipeline.make_preview(src, job_dir / "preview.mp4")
        with LOCK:
            PREVIEWS.pop(job_id, None)
    except Exception as e:
        traceback.print_exc()
        msg = str(e) if isinstance(e, RuntimeError) and not str(e).startswith("Command failed") else \
            "Couldn't prepare the video for choosing a scene. You can still type the From and To times."
        with LOCK:
            PREVIEWS[job_id] = msg


def start_preview(job_id):
    """Make preview.mp4 in the background unless it exists or is being made. Returns its state."""
    if (JOBS_DIR / job_id / "preview.mp4").exists():
        return "ready"
    with LOCK:
        state = PREVIEWS.get(job_id)
        if state == "building":
            return "building"
        PREVIEWS[job_id] = "building"
    threading.Thread(target=build_preview, args=(job_id,), daemon=True).start()
    return "building"


@app.post("/api/preview/<job_id>")
def preview(job_id):
    """Start making the preview if needed; the page calls this again until it's ready."""
    with LOCK:
        job = load_job(job_id)
        failed = PREVIEWS.get(job_id) not in (None, "building")
    if not job:
        abort(404)
    if failed and not (request.get_json(silent=True) or {}).get("retry"):
        return jsonify(status="error", error=PREVIEWS[job_id])
    state = start_preview(job_id)
    return jsonify(status=state, url=f"/media/{job_id}/preview.mp4" if state == "ready" else None)
