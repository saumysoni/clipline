"""
Hook controls: 3 new hook options, and re-rendering a Short with the chosen hook (or none).
"""
import json
import threading
import traceback

from flask import abort, jsonify, request

import pipeline
from settings import JOBS_DIR

from web.server import app
from web.store import JOBS, LOCK, RETRY_LOCKS, editable_job, load_job, next_file_number, update, update_short


def rerender_hook(job_id, idx, hook, mode, style, thumb=True):
    """Burn a different hook (or none) into one Short. Same moment, same face position, new file."""
    job_dir = JOBS_DIR / job_id
    with LOCK:
        lock = RETRY_LOCKS.setdefault(job_id, threading.Lock())
    try:
        with lock:
            update_short(job_id, idx, retry_msg="Updating the hook")
            with LOCK:
                job = json.loads(json.dumps(JOBS[job_id]))
            me = next(s for s in job["shorts"] if s["idx"] == idx)
            src = next(job_dir.glob("source.*"), None)
            tr_path = job_dir / "transcript.json"
            if not src or not tr_path.exists():
                raise RuntimeError("This vlog's video was deleted, so the hook can't be changed (it's part of the "
                                   "video). Upload the vlog again to change it.")
            tr = json.loads(tr_path.read_text(encoding="utf-8"))
            moment = {**me, "hook": hook, "hook_mode": mode}
            pipeline.prepare_job_fonts(job_dir)
            meta, num = pipeline.probe(src), next_file_number(job)
            video, cx = pipeline.render_short(src, meta, moment, tr["words"], num, job.get("style", "bold"),
                                              job_dir, cx=me.get("cx", "find"))
            extra = {}
            if thumb and mode == "text":
                update_short(job_id, idx, retry_msg="Updating the thumbnail")
                l1, l2 = pipeline.hook_to_lines(hook)
                name, work = pipeline.retext_thumbnail(src, meta, {**moment, "thumb_line1": l1, "thumb_line2": l2},
                                                       cx, num, job_dir)
                extra = {"thumb": name, "thumb_line1": l1, "thumb_line2": l2, **({"thumb_work": work} if work else {})}
        hooks = dict(me.get("hooks") or {})
        if mode == "text" and style == "custom":
            hooks["custom"] = hook
        update_short(job_id, idx, video=video, cx=cx, hook=hook if mode == "text" else me.get("hook", ""),
                     hook_mode=mode, hook_style=style, hooks=hooks, retrying=False, retry_msg=None, **extra)
    except Exception as e:
        traceback.print_exc()
        update_short(job_id, idx, retrying=False, retry_error=str(e))


@app.post("/api/hook/<job_id>/<int:idx>")
def set_hook(job_id, idx):
    """Show this hook text on the Short (mode "text"), or no text hook (mode "none")."""
    data = request.get_json(silent=True) or {}
    mode = "none" if data.get("mode") == "none" else "text"
    hook = " ".join(str(data.get("text", "")).split())[:60]
    style = str(data.get("style", "custom"))[:20]
    thumb = data.get("thumb", True) is not False
    if mode == "text" and not hook:
        return jsonify(error="Type a hook, or choose No text hook."), 400
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
    threading.Thread(target=rerender_hook, args=(job_id, idx, hook, mode, style, thumb), daemon=True).start()
    return jsonify(ok=True)


@app.post("/api/hooks/<job_id>/<int:idx>")
def new_hooks(job_id, idx):
    """Three fresh hook options for a Short (nothing is re-rendered until one is applied)."""
    note = str((request.get_json(silent=True) or {}).get("note", ""))[:300]
    with LOCK:
        job = load_job(job_id)
        if not job or job.get("status") != "ready":
            abort(400)
        me = next((s for s in job["shorts"] if s["idx"] == idx and not s.get("pending")), None)
        if not me:
            abort(404)
        me = dict(me)
    try:
        tr = json.loads((JOBS_DIR / job_id / "transcript.json").read_text(encoding="utf-8"))
        out = pipeline.rewrite_hooks(tr, me, note, job.get("vlog"))
    except (OSError, RuntimeError) as e:
        return jsonify(error=str(e) if isinstance(e, RuntimeError) else "The transcript for this job is gone."), 400
    hooks = {**out["hooks"], **({"custom": me["hooks"]["custom"]} if (me.get("hooks") or {}).get("custom") else {})}
    update_short(job_id, idx, hooks=hooks)
    return jsonify(hooks=hooks, pick=out["hook_style"])
