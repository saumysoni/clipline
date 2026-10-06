"""
New vlog (Vlogs page): upload a whole vlog to YouTube with AI help, and later make its Shorts from it.

  1. /api/vlog/start receives the video (file or Google Drive link) and, in the background, transcribes it
     (the transcript is kept, so its Shorts later skip transcribing), writes title ideas, a description with
     chapters and tags (pipeline/vlog_meta.py) and designs a 16:9 thumbnail (pipeline/vlog_thumbnail.py).
  2. The creator edits everything on the upload page; /draft saves it as they type.
  3. /upload sends it to YouTube (public now, scheduled, unlisted or private) in the background.
  4. /shorts makes its Shorts & Reels from the same video, while it's still kept (web/retention.py, 72 h).

A vlog job: kind "vlog", stages VLOG_STAGES while it's prepared, then status "ready" with job["vdraft"]
(titles, title, description, tags, thumb, look) and, once sent, job["vpost"] ({"state": uploading | done |
error, "pct", "video_id", "channel", "privacy", "when", "note", "error"}).
"""
import json
import re
import threading
import time
import traceback
import uuid
from pathlib import Path

from flask import abort, g, jsonify, request

import pipeline
import youtube as yt
from settings import JOBS_DIR

from pipeline.transcript_cache import find_saved_transcript, remember_transcript
from web.errors import plain_error
from web.server import app
from web.store import JOBS, LOCK, STAGES, load_job, update

VLOG_STAGES = ["Getting your vlog", "Transcribing", "Writing the title, description and chapters", "Designing the thumbnail"]
UPLOADING = set()  # vlog jobs being sent to YouTube right now


def prepare_vlog(job_id, src, link):
    job_dir = JOBS_DIR / job_id
    try:
        update(job_id, stage=0, pct=0, msg="Getting your vlog")
        if link:
            import gdown
            src = job_dir / "source.mp4"
            gdown.download(url=link, output=str(src), quiet=True, fuzzy=True)
            if not src.exists() or src.stat().st_size < 1000:
                raise RuntimeError("Couldn't download that link. Make sure sharing is set to "
                                   "'Anyone with the link', or upload the file instead.")
        meta = pipeline.probe(src)
        update(job_id, duration=meta["duration"], width=meta["width"], height=meta["height"])

        update(job_id, stage=1, pct=0, msg="Transcribing")
        job_tr = job_dir / "transcript.json"
        saved = find_saved_transcript(src)
        if saved and not job_tr.exists():
            import shutil
            shutil.copy(saved, job_tr)
        tr = pipeline.transcribe(src, job_tr, lambda p, m: update(job_id, pct=p, msg=m))
        remember_transcript(src, job_tr)

        update(job_id, stage=2, pct=0, msg="Writing the title, description and chapters")
        with LOCK:
            note = (JOBS.get(job_id) or {}).get("note", "")
        try:
            m = pipeline.write_vlog_meta(tr, {"note": note}, lambda p, msg: update(job_id, pct=p, msg=msg))
        except Exception as e:  # noqa: BLE001  (the AI is busy or has no key: the creator writes them)
            print("Vlog details without AI:", repr(e)[:300])
            m = {"titles": [], "text": "", "chapters": [], "hashtags": [], "description": "", "tags": [],
                 "thumb_line1": "", "thumb_line2": "", "ai_failed": True}

        update(job_id, stage=3, pct=0, msg="Designing the thumbnail")
        with LOCK:
            name = (JOBS.get(job_id) or {}).get("name", "")
        title = (m["titles"] or [name])[0]
        thumb = pipeline.make_vlog_thumbnail(src, meta["duration"], job_dir, title, m["thumb_line1"], m["thumb_line2"])
        done = time.time()  # the video is kept from here (KEEP_ORIGINAL_HOURS, web/retention.py)
        update(job_id, stage=len(VLOG_STAGES), pct=100, msg="Ready", status="ready", last_edit_at=done,
               vdraft={**m, "title": title, "thumb": thumb, "look": "frame"})
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        with LOCK:
            j = JOBS.get(job_id) or {}
            stages = j.get("stages") or [""]
            doing = stages[min(j.get("stage", 0), len(stages) - 1)]
        update(job_id, status="error", error=plain_error(e, doing), error_detail=str(e)[:4000])


@app.post("/api/vlog/start")
def vlog_start():
    link = (request.form.get("link") or "").strip()
    note = (request.form.get("note") or "").strip()[:1000]
    f = request.files.get("video")
    has_file = bool(f and f.filename)
    if link and not has_file and yt.video_link_problem(link):
        return jsonify(error=yt.video_link_problem(link), field="link"), 400
    if not has_file and not link:
        return jsonify(error="Add a video file or a Google Drive link."), 400
    job_id = uuid.uuid4().hex[:10]
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir()
    src, name = None, "Your vlog"
    if has_file:
        src = job_dir / f"source{Path(f.filename).suffix.lower() or '.mp4'}"
        f.save(src)
        name = Path(f.filename).stem
    with LOCK:
        JOBS[job_id] = {"id": job_id, "owner": g.user["id"], "created_at": time.time(), "kind": "vlog",
                        "status": "working", "stage": 0, "pct": 0, "msg": "", "stages": VLOG_STAGES,
                        "name": name, "note": note, "shorts": [], "vlog": {}}
    threading.Thread(target=prepare_vlog, args=(job_id, src, link), daemon=True).start()
    return jsonify(id=job_id)


def _vlog_job(job_id, need_video=True):
    """(job copy, error response or None). Call with LOCK held."""
    job = load_job(job_id)
    if not job or job.get("kind") != "vlog":
        abort(404)
    if job.get("status") != "ready":
        return None, (jsonify(error="Wait until the vlog is ready."), 400)
    if need_video and (job.get("video_deleted_at") or not next((JOBS_DIR / job_id).glob("source.*"), None)):
        return None, (jsonify(error="Pit Crew no longer has this vlog's video (it's deleted 72 hours after the "
                                    "last change, to keep storage free). Upload it again."), 400)
    return json.loads(json.dumps(job, default=str)), None


def _clean_draft(data, old):
    d = dict(old or {})
    if "title" in data:
        d["title"] = " ".join(str(data.get("title") or "").split())[:100]
    if "description" in data:
        d["description"] = str(data.get("description") or "")[:5000]
    if "tags" in data:
        tags = data.get("tags")
        tags = tags if isinstance(tags, list) else str(tags or "").split(",")
        d["tags"] = pipeline.clean_vlog_tags(tags)
    return d


@app.post("/api/vlog/<job_id>/draft")
def vlog_draft(job_id):
    """Save what the creator typed (title, description, tags), so leaving the page loses nothing."""
    data = request.get_json(force=True)
    with LOCK:
        job, err = _vlog_job(job_id, need_video=False)
    if err:
        return err
    update(job_id, vdraft=_clean_draft(data, job.get("vdraft")))
    return jsonify(ok=True)


@app.post("/api/vlog/<job_id>/look")
def vlog_look(job_id):
    """Switch the thumbnail between the Frame and Duotone looks (no AI)."""
    look = (request.get_json(force=True) or {}).get("look")
    if look not in ("frame", "duotone"):
        return jsonify(error="Pick Frame or Duotone."), 400
    with LOCK:
        job, err = _vlog_job(job_id, need_video=False)
    if err:
        return err
    try:
        name = pipeline.redraw_vlog_thumbnail(JOBS_DIR / job_id, look=look)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return jsonify(error="Couldn't redraw the thumbnail. Try again."), 500
    update(job_id, vdraft={**(job.get("vdraft") or {}), "thumb": name, "look": look})
    return jsonify(ok=True, thumb=name)


def _send(user_id, job_id, draft, privacy, when, channel):
    job_dir = JOBS_DIR / job_id
    try:
        service = yt.get_service(user_id, channel)
        src = next(job_dir.glob("source.*"))
        vid, note = yt.upload_vlog(service, src, draft["title"], draft["description"], draft.get("tags") or [],
                                   privacy, when, job_dir / draft["thumb"] if draft.get("thumb") else None,
                                   progress=lambda p: _post(job_id, pct=round(p, 1)))
        own = (yt.account(user_id).get("channel") or {})
        _post(job_id, state="done", pct=100, video_id=vid, note=note, sent_at=time.time())
        with LOCK:
            vlog = dict((JOBS.get(job_id) or {}).get("vlog") or {})
        vlog.update(title=draft["title"], description=draft["description"], tags=draft.get("tags") or [],
                    video_id=vid, youtube_url=f"https://www.youtube.com/watch?v={vid}",
                    channel=own.get("title", ""), channel_handle=own.get("handle", ""))
        update(job_id, vlog=vlog)
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        _post(job_id, state="error", error=yt.upload_error_message(e))
    finally:
        UPLOADING.discard(job_id)


def _post(job_id, **kw):
    with LOCK:
        cur = dict((JOBS.get(job_id) or {}).get("vpost") or {})
    cur.update(kw)
    update(job_id, vpost=cur)


@app.post("/api/vlog/<job_id>/upload")
def vlog_upload(job_id):
    data = request.get_json(force=True)
    with LOCK:
        job, err = _vlog_job(job_id)
        if err:
            return err
        if job_id in UPLOADING or (job.get("vpost") or {}).get("state") == "uploading":
            return jsonify(error="It's already being sent to YouTube."), 400
        if (job.get("vpost") or {}).get("state") == "done":
            return jsonify(error="This vlog is already on YouTube."), 400
    draft = _clean_draft(data, job.get("vdraft"))
    if not draft.get("title"):
        return jsonify(error="Give the vlog a title.", field="title"), 400
    acct = yt.account(g.user["id"])
    if not acct.get("signed_in"):
        return jsonify(error="Connect YouTube first, so Pit Crew knows which channel to upload to.", signin=True), 400
    channel = data.get("channel") or (acct.get("channel") or {}).get("id")
    if channel and not re.fullmatch(r"UC[\w-]{22}", str(channel)):
        channel = None
    privacy = data.get("privacy") if data.get("privacy") in ("public", "unlisted", "private", "schedule") else "public"
    when = None
    if privacy == "schedule":
        try:
            when = yt.plan_times(1, "custom", data.get("tz"), data.get("start"))[0]
        except RuntimeError as e:
            return jsonify(error=str(e), field="start"), 400
    with LOCK:
        UPLOADING.add(job_id)
    update(job_id, vdraft=draft, vpost={"state": "uploading", "pct": 0, "channel": channel, "privacy": privacy,
                                        "when": when.isoformat() if when else None, "error": ""})
    threading.Thread(target=_send, args=(g.user["id"], job_id, draft, privacy, when, channel), daemon=True).start()
    return jsonify(ok=True)


@app.post("/api/vlog/<job_id>/shorts")
def vlog_shorts(job_id):
    """Make Shorts & Reels from a vlog Pit Crew still has (an uploaded one, within 72 hours). Its transcript is
    reused and its Shorts link to it on YouTube."""
    from web.make_shorts import make_shorts

    data = request.get_json(force=True)
    with LOCK:
        job = load_job(job_id)
        if not job:
            abort(404)
        if job.get("status") == "working":
            return jsonify(error="This vlog is still being worked on. Wait until it's ready."), 400
        if [s for s in job.get("shorts", []) if not s.get("pending")]:
            return jsonify(error="This vlog already has Shorts. Open it to add more."), 400
        src = next((JOBS_DIR / job_id).glob("source.*"), None)
        if job.get("video_deleted_at") or not src:
            return jsonify(error="Pit Crew no longer has this vlog's video (it's deleted 72 hours after the last "
                                 "change, to keep storage free). Choose New video file and upload it again."), 400
        if job_id in UPLOADING:
            return jsonify(error="Wait until the vlog has finished uploading to YouTube."), 400
    count = max(1, min(10, int(data.get("count") or 5)))
    style = data.get("style") if data.get("style") in ("bold", "boxed", "clean") else "bold"
    note = str(data.get("note") or "").strip()[:1000]
    vlog = dict(job.get("vlog") or {})
    if not vlog.get("title"):
        vlog["title"] = (job.get("vdraft") or {}).get("title") or job.get("name", "")
    vlog.setdefault("description", (job.get("vdraft") or {}).get("description", ""))
    update(job_id, status="working", stage=0, pct=0, msg="", stages=STAGES, count=count, style=style,
           schedule="d18", note=note, must=[], vlog=vlog, error="", shorts=[])
    threading.Thread(target=make_shorts, args=(job_id, src, None, count, style, vlog, note, ()), daemon=True).start()
    return jsonify(ok=True)
