"""AI suggestions on the video upload page: /api/vlog/<id>/suggest (pipeline/vlog_suggest.py). Nothing is saved until the creator
picks one. The draft and its transcript are the creator's own, never data read from YouTube's API (gotcha 29)."""
import json
import traceback

from flask import jsonify, request

import pipeline
from settings import JOBS_DIR

from web.server import app
from web.store import LOCK
from web.vlog_upload import _vlog_job


@app.post("/api/vlog/<job_id>/suggest")
def vlog_suggest(job_id):
    data = request.get_json(force=True) or {}
    with LOCK:
        job, err = _vlog_job(job_id, need_video=False)
    if err:
        return err
    field = data.get("field")
    if field not in pipeline.VLOG_FIELDS:
        return jsonify(error="Choose the title, the description or the tags."), 400
    draft = {**(job.get("vdraft") or {})}
    for k in ("title", "description"):  # what's in the field now, even if not saved yet
        if isinstance(data.get(k), str):
            draft[k] = data[k]
    if isinstance(data.get("tags"), list):
        draft["tags"] = [str(t) for t in data["tags"]]
    tr_file, transcript = JOBS_DIR / job_id / "transcript.json", None
    try:
        transcript = json.loads(tr_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    try:
        return jsonify(items=pipeline.suggest_vlog_text(field, data.get("ask"), draft, transcript))
    except RuntimeError as e:
        return jsonify(error=str(e)), 400
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return jsonify(error="The AI is busy right now. Try again in a minute."), 503
