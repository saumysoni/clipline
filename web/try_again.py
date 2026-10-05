"""
Try again: remakes one Short (a new moment from the AI, or the creator's own times).
"""
import json
import threading
import time
import traceback

from flask import abort, jsonify, request

import pipeline
from settings import JOBS_DIR

from web.server import app
from web.store import JOBS, LOCK, RETRY_LOCKS, editable_job, next_file_number, update, update_short
from web.times import read_times


def remake_short(job_id, idx, note, times=None):
    """Make a new Short in slot `idx`: a moment the AI picks (Try again, Add with a description)
    or the creator's own times. Slots marked "pending" are new ones from Add a Short."""
    job_dir = JOBS_DIR / job_id
    with LOCK:
        lock = RETRY_LOCKS.setdefault(job_id, threading.Lock())
    try:
        with lock:
            say = lambda pct, msg: update_short(job_id, idx, retry_msg=msg)  # noqa: E731
            say(0, "Finding the moment")
            with LOCK:
                job = json.loads(json.dumps(JOBS[job_id]))
            me = next(s for s in job["shorts"] if s["idx"] == idx)
            taken = [s for s in job["shorts"] if s["idx"] != idx and not s.get("pending")]
            rejected = me.get("tried", []) + ([] if me.get("pending") else [{"start": me["start"], "end": me["end"]}])
            src = next(job_dir.glob("source.*"), None)
            tr_path = job_dir / "transcript.json"
            if not src or not tr_path.exists():
                raise RuntimeError("This vlog's video was deleted, so Pit Crew can't cut a new Short from it. "
                                   "Upload the vlog again to make new Shorts from it.")
            tr = json.loads(tr_path.read_text(encoding="utf-8"))
            if times:
                m = pipeline.manual_moment(tr, *times, note, say, context=job.get("vlog"))
            else:
                m = pipeline.repick_moment(tr, taken, rejected, note, say, context=job.get("vlog"), current=me)

            num = next_file_number(job)
            meta = pipeline.probe(src)
            pipeline.prepare_job_fonts(job_dir)
            say(0, "Editing the Short")
            video, cx = pipeline.render_short(src, meta, m, tr["words"], num, job.get("style", "bold"), job_dir)
            say(0, "Designing the thumbnail")
            thumb = pipeline.make_thumbnail(src, meta, m, cx, num, job_dir, tr["words"], job.get("vlog"))
        with LOCK:
            job = JOBS[job_id]
            job["last_edit_at"] = time.time()
            job["shorts"] = [{**m, "idx": idx, "video": video, "thumb": thumb, "keep": True, "tried": rejected, "cx": cx,
                              "edited_at": job["last_edit_at"]} if s["idx"] == idx else s for s in job["shorts"]]
            (job_dir / "job.json").write_text(json.dumps(job, default=str), encoding="utf-8")
    except Exception as e:
        traceback.print_exc()
        with LOCK:
            pending = any(s["idx"] == idx and s.get("pending") for s in JOBS[job_id]["shorts"])
        if pending:  # a new Short that couldn't be made: drop its card and say why
            with LOCK:
                job = JOBS[job_id]
                job["shorts"] = [s for s in job["shorts"] if s["idx"] != idx]
                job["add_error"] = str(e)
                (job_dir / "job.json").write_text(json.dumps(job, default=str), encoding="utf-8")
        else:
            update_short(job_id, idx, retrying=False, retry_error=str(e))


@app.post("/api/retry/<job_id>/<int:idx>")
def retry(job_id, idx):
    data = request.get_json(silent=True) or {}
    note = str(data.get("note", ""))[:500]
    try:
        times = read_times(data.get("start"), data.get("end"))
    except RuntimeError as e:
        return jsonify(error=str(e)), 400
    with LOCK:
        job, problem = editable_job(job_id)
        if problem:
            return problem
        me = next((s for s in job["shorts"] if s["idx"] == idx), None)
        if not me:
            abort(404)
        if me.get("retrying"):
            return jsonify(error="This Short is already being remade."), 400
    if job.get("upload_status") == "error":
        update(job_id, upload_status=None)  # the page shows the review screen again while remaking
    update_short(job_id, idx, retrying=True, retry_msg="Waiting for the other Short to finish",
                 retry_error=None)
    threading.Thread(target=remake_short, args=(job_id, idx, note, times), daemon=True).start()
    return jsonify(ok=True)
