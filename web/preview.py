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
PREVIEW_PCT = {}  # job id -> how far making it has got (0-100)
VIDEO_GONE = "This vlog's video was deleted, so it can't be played here. Upload the vlog again to choose moments on it."


def build_preview(job_id):
    job_dir = JOBS_DIR / job_id
    try:
        src = next(job_dir.glob("source.*"), None)
        if not src:
            raise RuntimeError(VIDEO_GONE)
        def progress(pct):
            if not src.exists():  # the vlog was stopped, deleted or its video removed: stop making the copy
                raise RuntimeError(VIDEO_GONE)
            PREVIEW_PCT[job_id] = round(pct)
        pipeline.make_preview(src, job_dir / "preview.mp4", progress)
        if not src.exists():  # the video was deleted while the copy was being made: don't keep the copy either
            (job_dir / "preview.mp4").unlink(missing_ok=True)
        with LOCK:
            PREVIEWS.pop(job_id, None)
            PREVIEW_PCT.pop(job_id, None)
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
    """What "Choose on the video" plays: the small copy if it exists (quickest to scrub), else the original itself
    ("source": the page tries it, and asks again with source_failed if this browser can't play it), else the copy
    is made now and the page calls this again until it's ready."""
    data = request.get_json(silent=True) or {}
    with LOCK:
        job = load_job(job_id)
        failed = PREVIEWS.get(job_id) not in (None, "building")
    if not job:
        abort(404)
    src = next((JOBS_DIR / job_id).glob("source.*"), None)
    if not src and not (JOBS_DIR / job_id / "preview.mp4").exists():
        return jsonify(status="error", error=VIDEO_GONE)
    if not (JOBS_DIR / job_id / "preview.mp4").exists() and src and not data.get("source_failed"):
        return jsonify(status="source", url=f"/media/{job_id}/{src.name}")
    if failed and not data.get("retry"):
        return jsonify(status="error", error=PREVIEWS[job_id])
    state = start_preview(job_id)
    return jsonify(status=state, url=f"/media/{job_id}/preview.mp4" if state == "ready" else None,
                   pct=PREVIEW_PCT.get(job_id, 0) if state == "building" else None)
