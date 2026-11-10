"""
Text & Overlays in the editor (js/overlays.js): text a creator puts on a draft Short at a moment they choose
(pipeline/overlays.py), burned in with the captions.

  GET  /api/overlays/<job>/<idx>   the Short's text on screen (saved, else []), the styles, sizes, fonts and ways in, the
                                   most a Short can have, and whether the Short can be remade now
  POST /api/overlays/<job>/<idx>   {"overlays": [...], "remake": true | false}: saves them; remake = make the Short again
                                   with them in the background ("retrying" until it's done). The editor saves without a
                                   remake when a cut, a new hook, the captions or the framing remake it anyway.

The exact frame is Captions' preview (/api/captions/<job>/<idx>/preview, which takes "overlays"). Text is part of the
video, so changing it needs the vlog's video or the Short's clean clip (gotchas 21, 35). Every other remake keeps it (it's
on the moment); Try again makes a new moment, so its text goes (it was put on the old moment's times).
"""
import threading

from flask import abort, jsonify, request

import pipeline

from web.captions import NO_VIDEO as _CAP_NO_VIDEO, _remake, _short, _transcript, _why_not
from web.server import app
from web.store import LOCK, editable_job, update, update_short

NO_VIDEO = _CAP_NO_VIDEO.replace("the captions can't be changed (they're", "the text on it can't be changed (it's")


def _duration(job, tr):
    return float(job.get("duration") or (tr or {}).get("duration") or 0)


@app.get("/api/overlays/<job_id>/<int:idx>")
def overlays_info(job_id, idx):
    with LOCK:
        job, me = _short(job_id, idx)
    why_not = _why_not(job_id, job, me)
    return jsonify(overlays=pipeline.clean_overlays(me.get("overlays"), _duration(job, _transcript(job_id))) or [],
                   styles=[{"id": k, "name": v[0]} for k, v in pipeline.OVERLAY_STYLES.items()],
                   sizes=list(pipeline.OVERLAY_SIZES.items()), anims=list(pipeline.OVERLAY_ANIMS),
                   fonts=[{"id": k, "name": name} for k, (name, _) in pipeline.CAPTION_FONTS.items()],
                   max=pipeline.OVERLAY_MAX, can_apply=not why_not, why_not=why_not.replace(_CAP_NO_VIDEO, NO_VIDEO),
                   remaking=bool(me.get("retrying")))


@app.post("/api/overlays/<job_id>/<int:idx>")
def overlays_save(job_id, idx):
    data = request.get_json(silent=True) or {}
    if not isinstance(data.get("overlays"), list):
        return jsonify(error="That text couldn't be read. Reload the page and try again."), 400
    with LOCK:
        job, problem = editable_job(job_id)
        if problem:
            return problem
        me = next((s for s in job["shorts"] if s["idx"] == idx and not s.get("pending")), None)
        if not me:
            abort(404)
        if me.get("retrying"):
            return jsonify(error="This Short is still being made. Wait a moment."), 400
    if _why_not(job_id, job, me):
        return jsonify(error=NO_VIDEO), 400
    ov = pipeline.clean_overlays(data["overlays"], _duration(job, _transcript(job_id)))
    if not data.get("remake"):
        update_short(job_id, idx, overlays=ov)
        return jsonify(ok=True, overlays=ov or [])
    if job.get("upload_status") == "error":
        update(job_id, upload_status=None)
    update_short(job_id, idx, overlays=ov, retrying=True, retry_msg="Waiting for the other Short to finish", retry_error=None)
    threading.Thread(target=_remake, args=(job_id, idx, "Adding the text", "Couldn't add the text to the Short. Please try again."),
                     daemon=True).start()
    return jsonify(ok=True, overlays=ov or [])
