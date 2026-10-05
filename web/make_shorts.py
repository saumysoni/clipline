"""
Make my Shorts: receives the upload and runs the whole pipeline for a new job in the background.
"""
import json
import os
import shutil
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from flask import g, jsonify, request

import pipeline
import youtube as yt
from settings import JOBS_DIR

from pipeline.transcript_cache import find_saved_transcript, remember_transcript
from web.errors import plain_error
from web.preview import start_preview
from web.server import app
from web.store import JOBS, LOCK, STAGES, update
from web.times import read_times


def make_shorts(job_id, src, link, count, style, vlog=None, note="", must=()):
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
            shutil.copy(saved, job_tr)
            update(job_id, pct=100, msg="Using the transcript saved from last time")
        tr = pipeline.transcribe(src, job_tr, lambda p, m: update(job_id, pct=p, msg=m))
        remember_transcript(src, job_tr)
        # Under ~60 words a minute, there's little speech to pick moments from (the page says so).
        update(job_id, little_speech=len(tr["words"]) < 60 * tr["duration"] / 60)

        update(job_id, stage=2, pct=0, msg="Finding the best moments")
        # The copy for "Choose on the video" starts now (the AI's turn is mostly waiting), so it's ready by Review.
        # Not needed when every browser can play the original as it is (the picker plays that instead).
        if not pipeline.plays_everywhere(src, meta):
            start_preview(job_id)
        vlog = dict(vlog or {})
        if vlog.get("youtube_url"):
            try:  # the page fills in title and description; this adds the video id and the channel's @handle
                with LOCK:
                    owner = JOBS[job_id].get("owner")
                info = yt.fetch_video_info(vlog["youtube_url"], yt.access_token(owner) if owner else None)
                vlog = {**info, **{k: v for k, v in vlog.items() if v}}
                update(job_id, vlog=vlog)
            except Exception as e:  # noqa: BLE001  (never fail a job over optional context)
                print(f"Couldn't read the vlog's YouTube info: {e}")
        say = lambda p, m: update(job_id, pct=p, msg=m)  # noqa: E731
        mine = []
        for k, (a, b) in enumerate(must, 1):
            say(5, f"Your moment {k} of {len(must)}")
            try:
                mine.append(pipeline.manual_moment(tr, a, b, note, say, context=vlog))
            except RuntimeError as e:
                raise RuntimeError(f"Must-have moment {k}: {e}") from e
        moments = mine + pipeline.pick_moments(tr, count - len(mine), say, context=vlog, note=note, taken=mine)
        update(job_id, moments_found=[{"start": m["start"], "end": m["end"]} for m in moments])

        pipeline.prepare_job_fonts(job_dir)
        # Each Short's thumbnail starts as soon as that Short is edited, and a few are designed side by
        # side (nearly all of a thumbnail's time is waiting for the AI), so they're mostly done when the
        # editing is. The page still shows editing first, then thumbnails.
        workers = max(1, int(os.getenv("THUMB_WORKERS", "3")))
        rendered, thumbs = [], []
        with ThreadPoolExecutor(workers) as pool:
            for i, m in enumerate(moments, 1):
                update(job_id, stage=3, pct=(i - 1) / len(moments) * 100,
                       msg=f"Editing Short {i} of {len(moments)}")
                video, cx = pipeline.render_short(src, meta, m, tr["words"], i, style, job_dir)
                rendered.append((video, cx))
                thumbs.append(pool.submit(pipeline.make_thumbnail, src, meta, m, cx, i, job_dir, tr["words"], vlog))
            shorts = []
            for i, (m, (video, cx), thumb) in enumerate(zip(moments, rendered, thumbs), 1):
                update(job_id, stage=4, pct=(i - 1) / len(moments) * 100,
                       msg=f"Thumbnail {i} of {len(moments)}")
                name = thumb.result()  # first: making the thumbnail also notes its look and folder on m
                shorts.append({**m, "idx": i, "video": video, "thumb": name, "keep": True, "cx": cx})
                update(job_id, shorts=shorts)
        done = time.time()  # the vlog's video and these drafts are kept from here (web/retention.py)
        update(job_id, stage=5, pct=100, msg="Done", status="ready", last_edit_at=done,
               shorts=[{**s, "edited_at": done} for s in shorts])
        if not pipeline.plays_everywhere(src, meta):
            start_preview(job_id)  # in case it failed earlier: tries once more (nothing if it's ready or under way)
    except Exception as e:
        traceback.print_exc()
        with LOCK:
            j = JOBS.get(job_id) or {}
            doing = (j.get("stages") or [""] * 9)[min(j.get("stage", 0), len(j.get("stages") or [""]) - 1)]
        update(job_id, status="error", error=plain_error(e, doing), error_detail=str(e)[:4000])


@app.post("/api/start")
def start():
    count = max(1, min(10, int(request.form.get("count", 5))))
    style = request.form.get("style", "bold")
    schedule = request.form.get("schedule", "d18")
    link = (request.form.get("link") or "").strip()
    note = (request.form.get("note") or "").strip()[:1000]
    try:
        rows = json.loads(request.form.get("must") or "[]")
        must = [t for k, r in enumerate(rows[:10], 1)
                if (t := read_times(r.get("start"), r.get("end"), f"must-have moment {k}"))]
    except RuntimeError as e:
        return jsonify(error=str(e), field="must"), 400
    except (ValueError, TypeError, AttributeError):
        return jsonify(error="The must-have moments couldn't be read. Check the times.", field="must"), 400
    count = min(10, max(count, len(must)))
    vlog = {
        "youtube_url": (request.form.get("yt_url") or "").strip()[:300],
        "title": (request.form.get("title") or "").strip()[:300],
        "description": (request.form.get("description") or "").strip()[:5000],
        "tags": [],
    }
    f = request.files.get("video")
    has_file = bool(f and f.filename)
    if link and not has_file and yt.video_link_problem(link):
        return jsonify(error=yt.video_link_problem(link), field="link"), 400
    if vlog["youtube_url"] and yt.youtube_link_problem(vlog["youtube_url"]):
        return jsonify(error=yt.youtube_link_problem(vlog["youtube_url"]), field="yt_url"), 400
    job_id = uuid.uuid4().hex[:10]
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir()
    src = None
    name = "Your vlog"
    if has_file:
        ext = Path(f.filename).suffix.lower() or ".mp4"
        src = job_dir / f"source{ext}"
        f.save(src)
        name = Path(f.filename).stem
    elif not link:
        return jsonify(error="Add a video file or a Google Drive link."), 400
    with LOCK:
        JOBS[job_id] = {"id": job_id, "owner": g.user["id"], "created_at": time.time(),
                        "status": "working", "stage": 0, "pct": 0, "msg": "",
                        "count": count, "style": style, "schedule": schedule, "name": name,
                        "stages": STAGES, "shorts": [], "vlog": vlog, "note": note,
                        "must": [{"start": a, "end": b} for a, b in must]}
    threading.Thread(target=make_shorts, args=(job_id, src, link, count, style, vlog, note, must),
                     daemon=True).start()
    return jsonify(id=job_id)
