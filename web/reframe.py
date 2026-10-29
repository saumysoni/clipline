"""
Reframe in the editor (js/reframe.js): what of the wide vlog a draft Short shows (pipeline/smart_reframe.py).

  GET  /api/reframe/<job>/<idx>          the Short's framing (saved, else None = the crop around the face it was made
                                         with, given as "face": x 0-1), the vlog's picture size, whether it's already
                                         vertical, and whether the Short can be remade now
  POST /api/reframe/<job>/<idx>          {"reframe": {...} | null, "remake": true | false}: saves it; remake = make the
                                         Short again with it in the background ("retrying" until it's done). The editor
                                         saves without a remake when another change remakes it anyway.
  POST /api/reframe/<job>/<idx>/follow   {"pieces" (what the Short will keep, if changed), "z"}: Follow the speaker =
                                         moves that keep the main face in the frame ([] and a note when none is found)
  POST /api/reframe/<job>/<idx>/auto     {"pieces"}: Auto layout per shot = {"shots", "moves"} (Fill on a face, Fit without)
  POST /api/reframe/<job>/<idx>/track    {"pieces", "at", "x", "y", "z"}: Tap to track = moves following what's at x, y
                                         from `at`, and "until" (where it was lost, or its part ends)

The preview is Captions' (/api/captions/<job>/<idx>/preview, which takes "reframe"): one frame of the Short as it will
be, hook and captions too. Framing is part of the video, so it needs the vlog's video (KEEP_ORIGINAL_HOURS, gotcha 21).
"""
import threading
import traceback

from flask import abort, jsonify, request

import pipeline

from web import clean_clips
from web.captions import NO_VIDEO as _CAP_NO_VIDEO, _remake, _short, _transcript, _why_not
from web.server import app
from web.store import LOCK, editable_job, update, update_short

NO_VIDEO = _CAP_NO_VIDEO.replace("the captions can't be changed (they're", "the framing can't be changed (it's")
FOLLOWS = threading.Semaphore(1)  # face finding at once (it reads the whole Short)


def _zoom_max(h):
    """How far in the page lets a creator zoom: less on a low-resolution vlog (a few hundred pixels blown up to 1920 is
    soft), at most REFRAME_ZOOM_MAX (1080p and up)."""
    return round(min(pipeline.REFRAME_ZOOM_MAX, max(1.25, h / 432)), 2)


def _duration(job, tr):
    return float(job.get("duration") or (tr or {}).get("duration") or 0)


@app.get("/api/reframe/<job_id>/<int:idx>")
def reframe_info(job_id, idx):
    with LOCK:
        job, me = _short(job_id, idx)
    src, why_not = clean_clips.source(job_id, job, me), _why_not(job_id, job, me)
    meta = None
    if src and not why_not:
        try:
            meta = pipeline.probe(src["path"])
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            why_not = "This vlog's video couldn't be read, so the framing can't be changed."
    w, h = (meta["width"], meta["height"]) if meta else (1920, 1080)
    cx = clean_clips.scaled_cx(me, src) if src else me.get("cx")  # in the source's pixels
    return jsonify(reframe=pipeline.clean_reframe(me.get("reframe"), _duration(job, _transcript(job_id))),
                   face=round(cx / w, 4) if isinstance(cx, (int, float)) and w else 0.5,
                   width=w, height=h, vertical=bool(meta and w / h <= 9 / 16 + 0.01),
                   zoom_max=_zoom_max(h), glide=pipeline.REFRAME_GLIDE,
                   can_apply=not why_not, why_not=why_not.replace(_CAP_NO_VIDEO, NO_VIDEO), remaking=bool(me.get("retrying")))


@app.post("/api/reframe/<job_id>/<int:idx>")
def reframe_save(job_id, idx):
    data = request.get_json(silent=True) or {}
    if data.get("reframe") is not None and not isinstance(data.get("reframe"), dict):
        return jsonify(error="That framing couldn't be read. Reload the page and try again."), 400
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
    rf = pipeline.clean_reframe(data.get("reframe"), _duration(job, _transcript(job_id)))
    if not data.get("remake"):
        update_short(job_id, idx, reframe=rf)
        return jsonify(ok=True, reframe=rf)
    if job.get("upload_status") == "error":
        update(job_id, upload_status=None)
    update_short(job_id, idx, reframe=rf, retrying=True, retry_msg="Waiting for the other Short to finish", retry_error=None)
    threading.Thread(target=_remake, args=(job_id, idx, "Reframing", "Couldn't reframe the Short. Please try again."),
                     daemon=True).start()
    return jsonify(ok=True, reframe=rf)


@app.post("/api/reframe/<job_id>/<int:idx>/follow")
def reframe_follow(job_id, idx):
    data = request.get_json(silent=True) or {}
    with LOCK:
        job, me = _short(job_id, idx)
    if _why_not(job_id, job, me):
        return jsonify(error=NO_VIDEO), 400
    src = clean_clips.source(job_id, job, me)
    pieces = pipeline.kept_pieces(me)
    try:
        if data.get("pieces"):
            pieces = pipeline.normalize_pieces(data["pieces"], 0, _duration(job, _transcript(job_id)) or 1e9) or pieces
        z = min(pipeline.REFRAME_ZOOM_MAX, max(1.0, float(data.get("z") or 1)))
    except (TypeError, ValueError, AttributeError):
        return jsonify(error="That couldn't be read. Reload the page and try again."), 400
    if not FOLLOWS.acquire(timeout=60):
        return jsonify(error="Pit Crew is busy following another Short. Try again in a moment."), 503
    try:
        moves = pipeline.follow_moves(src["path"], pipeline.probe(src["path"]), clean_clips.in_reach(pieces, src) or pieces, z,
                                      offset=src["offset"])
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        moves = []
    finally:
        FOLLOWS.release()
    note = "" if moves else "No face was found to follow in this Short. Move the frame by hand instead."
    return jsonify(moves=moves, note=note)


def _smart_args(job_id, idx, data):
    """(source, meta, pieces) for Auto layout and Tap to track, or an error response."""
    with LOCK:
        job, me = _short(job_id, idx)
    if _why_not(job_id, job, me):
        return None, (jsonify(error=NO_VIDEO), 400)
    src = clean_clips.source(job_id, job, me)
    pieces = pipeline.kept_pieces(me)
    try:
        if data.get("pieces"):
            pieces = pipeline.normalize_pieces(data["pieces"], 0, _duration(job, _transcript(job_id)) or 1e9) or pieces
    except (TypeError, ValueError, AttributeError):
        return None, (jsonify(error="That couldn't be read. Reload the page and try again."), 400)
    return (src, pipeline.probe(src["path"]), clean_clips.in_reach(pieces, src) or pieces), None


@app.post("/api/reframe/<job_id>/<int:idx>/auto")
def reframe_auto(job_id, idx):
    """Auto layout per shot: {"shots", "moves"} (a shot with a face framed on it, one without shown whole)."""
    data = request.get_json(silent=True) or {}
    args, problem = _smart_args(job_id, idx, data)
    if problem:
        return problem
    src, meta, pieces = args
    if not FOLLOWS.acquire(timeout=60):
        return jsonify(error="Pit Crew is busy with another Short. Try again in a moment."), 503
    try:
        out = pipeline.auto_shots(src["path"], meta, pieces, offset=src["offset"])
    finally:
        FOLLOWS.release()
    if not out.get("shots"):
        return jsonify(shots=[], moves=[], note="Pit Crew couldn't read the shots of this Short. Choose a layout yourself.")
    return jsonify(shots=out["shots"], moves=out["moves"], note="")


@app.post("/api/reframe/<job_id>/<int:idx>/track")
def reframe_track(job_id, idx):
    """Tap to track: {"at" (vlog seconds), "x", "y" (0-1), "z"} -> moves following what's there, and "until"."""
    data = request.get_json(silent=True) or {}
    args, problem = _smart_args(job_id, idx, data)
    if problem:
        return problem
    src, meta, pieces = args
    try:
        at, x, y = float(data["at"]), min(1, max(0, float(data["x"]))), min(1, max(0, float(data["y"])))
        z = min(pipeline.REFRAME_ZOOM_MAX, max(1.0, float(data.get("z") or 1)))
    except (KeyError, TypeError, ValueError):
        return jsonify(error="That couldn't be read. Reload the page and try again."), 400
    if not FOLLOWS.acquire(timeout=60):
        return jsonify(error="Pit Crew is busy with another Short. Try again in a moment."), 503
    try:
        moves, until = pipeline.track_moves(src["path"], meta, pieces, at, x, y, z, offset=src["offset"])
    finally:
        FOLLOWS.release()
    note = "" if len(moves) > 1 else "Pit Crew couldn't follow that. Try clicking right on it, where it stands out."
    return jsonify(moves=moves, until=until, note=note)
