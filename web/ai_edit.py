"""
AI Edit in the editor (js/ai-edit.js): which parts of a draft Short's moment it keeps (pipeline/ai_edit.py,
pipeline/pieces.py).

  GET  /api/ai-edit/<job>/<idx>            the Short's words (each with whether it's kept), what's kept, the pauses and
                                           filler words found, whether changes can be made now, and "near": the words
                                           NEAR seconds either side of the moment too (Trim's close-up: what a part can
                                           be stretched into, and snapping there)
  POST /api/ai-edit/<job>/<idx>/apply      {"pieces": [[a, b], ...] | null (the whole moment again)}: saves it and remakes
                                           the Short in the background (like a new hook: "retrying" until it's done)

The editor's timeline (Trim, js/editor.js) uses the same apply: its pieces can reach past the moment, anywhere in the
vlog, and the moment's start and end become the first piece's start and the last one's end. Remaking needs the vlog's
video (kept KEEP_ORIGINAL_HOURS, gotcha 21). After a cut a hook may quote something no longer said: it's dropped
(gotcha 13).
"""
import json
import threading
import traceback

from flask import abort, jsonify, request

import pipeline
from pipeline.manual_moment import MANUAL_MAX, MANUAL_MIN
from settings import JOBS_DIR

from web import clean_clips
from web.server import app
from web.store import JOBS, LOCK, RETRY_LOCKS, editable_job, load_job, next_file_number, update, update_short

NEAR = 30  # seconds of the vlog either side of the moment whose words Trim shows
NO_VIDEO = ("This vlog's video was deleted, so Pit Crew can't cut this Short again. You can still change its title, "
            "hashtags and thumbnail text.")


def _short(job_id, idx):
    """(job copy, Short copy) of a finished Short, or 404. Call with LOCK held."""
    job = load_job(job_id)
    if not job or job.get("status") != "ready":
        abort(404)
    me = next((s for s in job["shorts"] if s["idx"] == idx and not s.get("pending")), None)
    if not me:
        abort(404)
    return json.loads(json.dumps(job, default=str)), dict(me)


def _transcript(job_id):
    try:
        return json.loads((JOBS_DIR / job_id / "transcript.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _duration(job, tr):
    """How long the vlog is (seconds): how far the timeline can reach."""
    return round(float(job.get("duration") or tr.get("duration") or 0), 3)


def _source(job_id, job, me):
    return clean_clips.source(job_id, job, me)


@app.get("/api/ai-edit/<job_id>/<int:idx>")
def ai_edit_info(job_id, idx):
    with LOCK:
        job, me = _short(job_id, idx)
    tr = _transcript(job_id)
    if not tr:
        return jsonify(error="This Short's transcript is gone, so it can't be edited by its words."), 400
    pieces = pipeline.kept_pieces(me)
    fill = {(a, b) for a, b, _ in pipeline.find_fillers(tr["words"], me)}
    pos = {id(w): k for k, w in enumerate(tr["words"])}  # "i": the word's place in transcript.json (js/captions.js)
    words = [{"w": w["w"], "s": w["s"], "e": w["e"], "i": pos[id(w)],
              "kept": any(a <= (w["s"] + w["e"]) / 2 <= b for a, b in pieces),
              "filler": any(a <= w["s"] and w["e"] <= b for a, b in fill)} for w in pipeline.words_in(tr["words"], me)]
    src = _source(job_id, job, me)
    why_not = "" if src else NO_VIDEO
    reach = list(src["reach"]) if src else [0, _duration(job, tr)]
    reach[1] = min(reach[1], _duration(job, tr) or reach[1])
    near = [{"w": w["w"], "s": w["s"], "e": w["e"]} for w in
            pipeline.words_in(tr["words"], {"start": float(me["start"]) - NEAR, "end": float(me["end"]) + NEAR})]
    return jsonify(start=me["start"], end=me["end"], duration=_duration(job, tr), reach=reach, clip=bool(src and src["clip"]), pieces=[list(p) for p in pieces], length=pipeline.short_length(me),
                   near=near,
                   words=words, pauses={k: [list(p) for p in pipeline.find_pauses(tr["words"], me, k)] for k in ("long", "tight")},
                   fillers=[list(f) for f in pipeline.find_fillers(tr["words"], me)],
                   min=MANUAL_MIN, max=MANUAL_MAX, remaking=bool(me.get("retrying")), can_apply=not why_not, why_not=why_not,
                   note=me.get("edit_note") or "")


def _remake(job_id, idx, keep, start, end):
    """Render the Short again with these pieces (inside start..end, its moment from now on; same face position; the
    thumbnail stays), one change at a time."""
    job_dir = JOBS_DIR / job_id
    with LOCK:
        lock = RETRY_LOCKS.setdefault(job_id, threading.Lock())
    try:
        with lock:
            update_short(job_id, idx, retry_msg="Cutting the Short")
            with LOCK:
                job = json.loads(json.dumps(JOBS[job_id], default=str))
            me = next(s for s in job["shorts"] if s["idx"] == idx)
            src = _source(job_id, job, me)
            tr = _transcript(job_id)
            if not src or not tr:
                raise RuntimeError(NO_VIDEO)
            moment = {**me, "start": start, "end": end, "pieces": keep}
            fix, note = pipeline.honest_hooks(moment, pipeline.pieces_said(tr, moment))
            moment.update(fix)
            pipeline.prepare_job_fonts(job_dir)
            video, cx = clean_clips.render(src, moment, tr["words"], next_file_number(job), job.get("style", "bold"), job_dir, me)
        update_short(job_id, idx, video=video, cx=cx, start=start, end=end, pieces=keep, retrying=False, retry_msg=None,
                     edit_note=note, **fix)
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        update_short(job_id, idx, retrying=False, retry_error=str(e) if isinstance(e, RuntimeError)
                     else "Couldn't cut the Short. Please try again.")


@app.post("/api/ai-edit/<job_id>/<int:idx>/apply")
def ai_edit_apply(job_id, idx):
    data = request.get_json(silent=True) or {}
    with LOCK:
        job, problem = editable_job(job_id)
        if problem:
            return problem
        me = next((s for s in job["shorts"] if s["idx"] == idx and not s.get("pending")), None)
        if not me:
            abort(404)
        if me.get("retrying"):
            return jsonify(error="This Short is still being made. Wait a moment."), 400
    src = _source(job_id, job, me)
    if not src or not (JOBS_DIR / job_id / "transcript.json").exists():
        return jsonify(error=NO_VIDEO), 400
    s, e = float(me["start"]), float(me["end"])
    raw = data.get("pieces")
    try:
        dur = _duration(job, _transcript(job_id) or {}) or e
        # anywhere in the vlog (Trim), or in the Short's clean clip once the vlog's video is gone
        pieces = pipeline.normalize_pieces(raw, max(0, src["reach"][0]), min(dur, src["reach"][1])) if raw else [(s, e)]
    except (TypeError, ValueError, AttributeError):
        return jsonify(error="Those cuts couldn't be read. Reload the page and try again."), 400
    total = sum(b - a for a, b in pieces)
    if not pieces or total < MANUAL_MIN:
        return jsonify(error=f"That would leave less than {MANUAL_MIN} seconds. Keep a little more."), 400
    if total > MANUAL_MAX:
        return jsonify(error="A Short can be at most 3 minutes long."), 400
    ns, ne = pieces[0][0], pieces[-1][1]  # the moment from now on
    keep = None if len(pieces) == 1 else [list(p) for p in pieces]
    if (ns, ne) == (s, e) and keep == ([list(p) for p in pipeline.kept_pieces(me)] if me.get("pieces") else None):
        return jsonify(ok=True, unchanged=True)
    if job.get("upload_status") == "error":
        update(job_id, upload_status=None)
    update_short(job_id, idx, retrying=True, retry_msg="Waiting for the other Short to finish", retry_error=None)
    threading.Thread(target=_remake, args=(job_id, idx, keep, ns, ne), daemon=True).start()
    return jsonify(ok=True)
