"""
Captions in the editor (js/captions.js): how a draft Short's burned-in captions look and read (pipeline/captions.py).

  GET  /api/captions/<job>/<idx>           the Short's caption settings (saved, else its job's style), the presets and
                                           fonts, and whether the Short can be remade now
  POST /api/captions/<job>/<idx>           {"captions": {...}, "remake": true | false}: saves them; remake = make the
                                           Short again with them in the background ("retrying" until it's done). The
                                           editor saves without a remake when a cut or a new hook remakes it anyway.
  POST /api/captions/<job>/<idx>/preview   {"captions", "at" (vlog seconds), "pieces" (what the Short will keep, if
                                           changed), "reframe" (the framing, if changed), "motion"} -> one JPEG frame with them burned in, or with motion a
                                           few seconds of silent MP4 from there (lines coming in); nothing saved

Captions are part of the video, so changing them needs the vlog's video (kept KEEP_ORIGINAL_HOURS, gotcha 21). Every
other remake (hook, cut, Trim) keeps them; Try again keeps the look and drops word changes (web/try_again.py).
"""
import io
import json
import threading
import traceback

from flask import abort, jsonify, request, send_file

import pipeline
from settings import JOBS_DIR

from web import clean_clips
from web.server import app
from web.store import JOBS, LOCK, RETRY_LOCKS, editable_job, load_job, next_file_number, update, update_short

NO_VIDEO = ("This vlog's video was deleted, so the captions can't be changed (they're part of the video). "
            "You can still change its title, hashtags and thumbnail text.")
PREVIEWS = threading.Semaphore(2)  # previews at once (each is one FFmpeg run)


def _short(job_id, idx):
    """(job copy, Short copy) of a finished Short, or 404. Call with LOCK held."""
    job = load_job(job_id)
    if not job or job.get("status") != "ready":
        abort(404)
    me = next((s for s in job["shorts"] if s["idx"] == idx and not s.get("pending")), None)
    if not me:
        abort(404)
    return json.loads(json.dumps(job, default=str)), dict(me)


def _source(job_id, job, me):
    """The video to remake this Short from: the vlog, else its clean clip (web/clean_clips.py), else None."""
    return clean_clips.source(job_id, job, me)


def _transcript(job_id):
    try:
        return json.loads((JOBS_DIR / job_id / "transcript.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _why_not(job_id, job, me):
    ok = _source(job_id, job, me) and (JOBS_DIR / job_id / "transcript.json").exists()
    return "" if ok else NO_VIDEO


@app.get("/api/captions/<job_id>/<int:idx>")
def captions_info(job_id, idx):
    with LOCK:
        job, me = _short(job_id, idx)
    style = job.get("style", "bold")
    why_not = _why_not(job_id, job, me)
    return jsonify(captions=pipeline.clean_captions(me.get("captions"), style), style=style,
                   presets=[{"id": k, "name": name, "captions": pipeline.caption_preset(k)}
                            for k, (name, _) in pipeline.CAPTION_PRESETS.items()],
                   fonts=[{"id": k, "name": name} for k, (name, _) in pipeline.CAPTION_FONTS.items()],
                   can_apply=not why_not, why_not=why_not, remaking=bool(me.get("retrying")))


def _remake(job_id, idx, msg="Updating the captions", fail="Couldn't update the captions. Please try again."):
    """Make the Short again with its saved captions and framing (same moment, pieces, hook and face position; the
    thumbnail stays). web/reframe.py uses it too."""
    job_dir = JOBS_DIR / job_id
    with LOCK:
        lock = RETRY_LOCKS.setdefault(job_id, threading.Lock())
    try:
        with lock:
            update_short(job_id, idx, retry_msg=msg)
            with LOCK:
                job = json.loads(json.dumps(JOBS[job_id], default=str))
            me = next(s for s in job["shorts"] if s["idx"] == idx)
            src, tr = _source(job_id, job, me), _transcript(job_id)
            if not src or not tr:
                raise RuntimeError(NO_VIDEO)
            pipeline.prepare_job_fonts(job_dir)
            video, cx = clean_clips.render(src, me, tr["words"], next_file_number(job), job.get("style", "bold"), job_dir, me)
        update_short(job_id, idx, video=video, cx=cx, retrying=False, retry_msg=None)
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        update_short(job_id, idx, retrying=False, retry_error=str(e) if isinstance(e, RuntimeError)
                     else fail)


@app.post("/api/captions/<job_id>/<int:idx>")
def captions_save(job_id, idx):
    data = request.get_json(silent=True) or {}
    if not isinstance(data.get("captions"), dict):
        return jsonify(error="Those captions couldn't be read. Reload the page and try again."), 400
    with LOCK:
        job, problem = editable_job(job_id)
        if problem:
            return problem
        me = next((s for s in job["shorts"] if s["idx"] == idx and not s.get("pending")), None)
        if not me:
            abort(404)
        if me.get("retrying"):
            return jsonify(error="This Short is still being made. Wait a moment."), 400
    why_not = _why_not(job_id, job, me)
    if why_not:
        return jsonify(error=why_not), 400
    caps = pipeline.clean_captions(data["captions"], job.get("style", "bold"))
    if not data.get("remake"):
        update_short(job_id, idx, captions=caps)
        return jsonify(ok=True, captions=caps)
    if job.get("upload_status") == "error":
        update(job_id, upload_status=None)
    update_short(job_id, idx, captions=caps, retrying=True, retry_msg="Waiting for the other Short to finish",
                 retry_error=None)
    threading.Thread(target=_remake, args=(job_id, idx), daemon=True).start()
    return jsonify(ok=True, captions=caps)


@app.post("/api/captions/<job_id>/<int:idx>/preview")
def captions_preview(job_id, idx):
    data = request.get_json(silent=True) or {}
    with LOCK:
        job, me = _short(job_id, idx)
    if _why_not(job_id, job, me):
        return jsonify(error=NO_VIDEO), 400
    src, tr = _source(job_id, job, me), _transcript(job_id)
    style = job.get("style", "bold")
    moment = dict(me)
    try:
        at = float(data.get("at", me["start"]))
        if data.get("pieces"):
            dur = float(job.get("duration") or tr.get("duration") or me["end"])
            pieces = pipeline.normalize_pieces(data["pieces"], max(0, src["reach"][0]), min(dur, src["reach"][1]))
            if pieces:
                moment.update(start=pieces[0][0], end=pieces[-1][1], pieces=[list(p) for p in pieces])
    except (TypeError, ValueError, AttributeError):
        return jsonify(error="That preview couldn't be read. Reload the page and try again."), 400
    caps = pipeline.clean_captions(data.get("captions"), style)
    if "reframe" in data:  # the framing waiting in Reframe (js/reframe.js), if changed
        moment["reframe"] = pipeline.clean_reframe(data["reframe"], float(job.get("duration") or tr.get("duration") or 0))
    try:
        with PREVIEWS:
            pipeline.prepare_job_fonts(JOBS_DIR / job_id)
            make = pipeline.caption_clip if data.get("motion") else pipeline.caption_frame
            moment["cx"] = clean_clips.scaled_cx(me, src)
            if moment["cx"] == "find":
                moment["cx"] = None
            out = make(src["path"], pipeline.probe(src["path"]), moment, tr["words"], at, style, JOBS_DIR / job_id, caps,
                       offset=src["offset"])
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return jsonify(error="Couldn't draw the preview. Try again."), 500
    return send_file(io.BytesIO(out), mimetype="video/mp4" if data.get("motion") else "image/jpeg", max_age=0)
