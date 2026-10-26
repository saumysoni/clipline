"""
A draft Short's thumbnail, changed from Quick review and the editor (js/short-details.js):
- its text: redrawn from the frames and plan saved with it (pipeline.retext_thumbnail): no AI, about a second;
- Try again: a new thumbnail, the AI asked for another frame and other text than the last one (pipeline.make_thumbnail
  with avoid=), in the look the creator chose. Needs the vlog's video (new frames come from it).
Both run in the background like the look switch (web/thumbnail_look.py): the Short is "retrying" until it's done.
"""
import json
import threading
import traceback

from flask import abort, jsonify, request

import pipeline
from settings import JOBS_DIR

from web.server import app
from web.store import JOBS, LOCK, RETRY_LOCKS, editable_job, load_job, next_file_number, update, update_short

MAX_LINE = 30  # pipeline.thumbnails.plan.tidy_lines keeps 30 characters a line


def _short(job_id, idx):
    """(job, Short, error reply or None) for a change; call with LOCK held."""
    job, problem = editable_job(job_id)
    if problem:
        return None, None, problem
    me = next((s for s in job["shorts"] if s["idx"] == idx and not s.get("pending")), None)
    if not me:
        abort(404)
    if me.get("retrying"):
        return None, None, (jsonify(error="This Short is still being made. Wait a moment."), 400)
    return job, me, None


def _run(job_id, idx, msg, work):
    """work(job copy, Short copy, job folder) -> fields to save on the Short; in the background, one change at a time."""
    if (JOBS.get(job_id) or {}).get("upload_status") == "error":
        update(job_id, upload_status=None)
    update_short(job_id, idx, retrying=True, retry_msg="Waiting for the other Short to finish", retry_error=None)

    def go():
        with LOCK:
            lock = RETRY_LOCKS.setdefault(job_id, threading.Lock())
        try:
            with lock:
                update_short(job_id, idx, retry_msg=msg)
                with LOCK:
                    job = json.loads(json.dumps(JOBS[job_id]))
                me = next(s for s in job["shorts"] if s["idx"] == idx)
                fields = work(job, me, JOBS_DIR / job_id)
            update_short(job_id, idx, retrying=False, retry_msg=None, **fields)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            update_short(job_id, idx, retrying=False, retry_error=str(e) if isinstance(e, RuntimeError)
                         else "Couldn't change the thumbnail. Please try again.")
    threading.Thread(target=go, daemon=True).start()


def _source(job_dir):
    src = next(job_dir.glob("source.*"), None)
    return src, (pipeline.probe(src) if src else None)


@app.get("/api/thumb/<job_id>/<int:idx>")
def thumb_info(job_id, idx):
    """The thumbnail's text as drawn (the saved plan's, else the Short's), and what can be changed."""
    with LOCK:
        job = load_job(job_id)
        if not job:
            abort(404)
        me = next((s for s in job["shorts"] if s["idx"] == idx and not s.get("pending")), None)
        if not me:
            abort(404)
        has_video = any((JOBS_DIR / job_id).glob("source.*"))
    pl = pipeline.thumb_plan(me, JOBS_DIR / job_id) or {}
    return jsonify(line1=pl.get("line1", me.get("thumb_line1", "")), line2=pl.get("line2", me.get("thumb_line2", "")),
                   can_text=bool(pl) or has_video, can_again=has_video)


@app.post("/api/thumb-text/<job_id>/<int:idx>")
def thumb_text(job_id, idx):
    """Redraw the thumbnail with this text: {line1 (small line, may be empty), line2 (the headline)}."""
    data = request.get_json(silent=True) or {}
    l1, l2 = (" ".join(str(data.get(k) or "").split()) for k in ("line1", "line2"))
    if not l2:
        return jsonify(error="Type the headline for the thumbnail."), 400
    if len(l1) > MAX_LINE or len(l2) > MAX_LINE:
        return jsonify(error=f"Keep each line of the thumbnail under {MAX_LINE} characters, so it can be read on a phone."), 400
    with LOCK:
        job, me, problem = _short(job_id, idx)
        if problem:
            return problem
        if not pipeline.thumb_plan(me, JOBS_DIR / job_id) and not any((JOBS_DIR / job_id).glob("source.*")):
            return jsonify(error="This thumbnail can't be redrawn: the vlog's video was deleted. Upload the vlog again to change it."), 400

    def work(job, me, job_dir):
        src, meta = _source(job_dir)
        moment = {**me, "thumb_line1": l1, "thumb_line2": l2}
        name, folder = pipeline.retext_thumbnail(src, meta, moment, me.get("cx"), next_file_number(job), job_dir)
        return {"thumb": name, "thumb_line1": l1, "thumb_line2": l2, **({"thumb_work": folder} if folder else {})}
    _run(job_id, idx, "Redrawing the thumbnail", work)
    return jsonify(ok=True)


@app.post("/api/thumb-again/<job_id>/<int:idx>")
def thumb_again(job_id, idx):
    """A new thumbnail: another frame and other text, in the same look."""
    with LOCK:
        job, me, problem = _short(job_id, idx)
        if problem:
            return problem
        if not any((JOBS_DIR / job_id).glob("source.*")) or not (JOBS_DIR / job_id / "transcript.json").exists():
            return jsonify(error="This vlog's video was deleted, so Pit Crew can't pick a new frame. You can still "
                                 "change the thumbnail's text and look."), 400

    def work(job, me, job_dir):
        src, meta = _source(job_dir)
        tr = json.loads((job_dir / "transcript.json").read_text(encoding="utf-8"))
        old = pipeline.thumb_plan(me, job_dir)
        moment = dict(me)
        name = pipeline.make_thumbnail(src, meta, moment, me.get("cx"), next_file_number(job), job_dir, tr["words"],
                                       job.get("vlog"), avoid=old)
        fields = {"thumb": name, "thumb_work": moment.get("thumb_work"), "thumb_look": moment.get("thumb_look")}
        look = me.get("thumb_look")
        if look and moment.get("thumb_look") and look != moment["thumb_look"]:  # keep the look the creator chose
            with LOCK:
                job = json.loads(json.dumps(JOBS[job_id]))
            fields["thumb"], _ = pipeline.relook_thumbnail({**me, **fields}, next_file_number(job), job_dir, look)
            fields["thumb_look"] = look
        pl = pipeline.thumb_plan({**me, **fields}, job_dir) or {}
        if pl:
            fields.update(thumb_line1=pl.get("line1", ""), thumb_line2=pl.get("line2", ""))
        return {k: v for k, v in fields.items() if v is not None}
    _run(job_id, idx, "Making a new thumbnail", work)
    return jsonify(ok=True)
