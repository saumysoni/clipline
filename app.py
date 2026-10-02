"""
Clipline: run `python app.py`, then open http://localhost:8000
"""
import hashlib
import json
import logging
import re
import shutil
import threading
import traceback
import uuid
import webbrowser
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, request, send_from_directory

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

import pipeline  # noqa: E402  (load .env first)
import youtube_upload as yt  # noqa: E402

JOBS_DIR = ROOT / "jobs"
JOBS_DIR.mkdir(exist_ok=True)

app = Flask(__name__, static_folder=str(ROOT / "static"), static_url_path="/static")


class _HideStatusPolls(logging.Filter):
    """The page checks progress every second; don't print a line for each check."""
    def filter(self, record):
        return "/api/status/" not in record.getMessage()


logging.getLogger("werkzeug").addFilter(_HideStatusPolls())
app.config["MAX_CONTENT_LENGTH"] = None  # long 4K vlogs are big

JOBS = {}
LOCK = threading.Lock()
STAGES = ["Getting your vlog", "Transcribing", "Finding the best moments",
          "Editing Shorts", "Designing thumbnails"]


def update(job_id, **kw):
    with LOCK:
        JOBS[job_id].update(kw)
        (JOBS_DIR / job_id / "job.json").write_text(json.dumps(JOBS[job_id], default=str), encoding="utf-8")


# --------------------------------------------------------------------------- saved transcripts
# Transcribing a long vlog takes a while, so each transcript is also saved under
# jobs/_transcripts, named after a fingerprint of the video. Uploading the same video
# again (e.g. after a Gemini hiccup) reuses it instead of transcribing again.
TRANSCRIPTS_DIR = JOBS_DIR / "_transcripts"


def video_fingerprint(path):
    path = Path(path)
    size = path.stat().st_size
    h = hashlib.sha1(str(size).encode())
    with open(path, "rb") as f:
        h.update(f.read(4 << 20))
        if size > 8 << 20:
            f.seek(-(4 << 20), 2)
            h.update(f.read())
    return h.hexdigest()[:20]


def find_saved_transcript(src):
    try:
        fp = video_fingerprint(src)
        cached = TRANSCRIPTS_DIR / f"{fp}.json"
        if cached.exists():
            return cached
        # Older jobs (made before this feature) may already hold a transcript of this video.
        for other in JOBS_DIR.glob("*/transcript.json"):
            for vid in other.parent.glob("source.*"):
                if vid.resolve() != Path(src).resolve() and vid.stat().st_size == Path(src).stat().st_size \
                        and video_fingerprint(vid) == fp:
                    return other
    except OSError:
        pass
    return None


def remember_transcript(src, job_tr):
    try:
        TRANSCRIPTS_DIR.mkdir(exist_ok=True)
        cached = TRANSCRIPTS_DIR / f"{video_fingerprint(src)}.json"
        if Path(job_tr).exists() and not cached.exists():
            shutil.copy(job_tr, cached)
    except OSError:
        pass


# --------------------------------------------------------------------------- make Shorts
def make_shorts(job_id, src, link, count, style, vlog=None):
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

        update(job_id, stage=2, pct=0, msg="Finding the best moments")
        vlog = dict(vlog or {})
        if vlog.get("youtube_url") and not (vlog.get("title") and vlog.get("description")):
            try:  # the page normally fills these in already; this covers a skipped lookup
                info = yt.fetch_video_info(vlog["youtube_url"])
                vlog = {**info, **{k: v for k, v in vlog.items() if v}}
                update(job_id, vlog=vlog)
            except Exception as e:  # noqa: BLE001  (never fail a job over optional context)
                print(f"Couldn't read the vlog's YouTube info: {e}")
        moments = pipeline.pick_moments(tr, count, lambda p, m: update(job_id, pct=p, msg=m), context=vlog)
        update(job_id, moments_found=[{"start": m["start"], "end": m["end"]} for m in moments])

        pipeline.prepare_job_fonts(job_dir)
        shorts = []
        for i, m in enumerate(moments, 1):
            update(job_id, stage=3, pct=(i - 1) / len(moments) * 100,
                   msg=f"Editing Short {i} of {len(moments)}")
            video, cx = pipeline.render_short(src, meta, m, tr["words"], i, style, job_dir)
            update(job_id, stage=4, msg=f"Thumbnail {i} of {len(moments)}")
            thumb = pipeline.make_thumbnail(src, meta, m, cx, i, job_dir, tr["words"], vlog)
            shorts.append({**m, "idx": i, "video": video, "thumb": thumb, "keep": True})
            update(job_id, shorts=shorts)
        update(job_id, stage=5, pct=100, msg="Done", status="ready", shorts=shorts)
    except Exception as e:
        traceback.print_exc()
        update(job_id, status="error", error=str(e))


@app.post("/api/start")
def start():
    count = max(1, min(10, int(request.form.get("count", 5))))
    style = request.form.get("style", "bold")
    schedule = request.form.get("schedule", "d18")
    link = (request.form.get("link") or "").strip()
    vlog = {
        "youtube_url": (request.form.get("yt_url") or "").strip()[:300],
        "title": (request.form.get("title") or "").strip()[:300],
        "description": (request.form.get("description") or "").strip()[:5000],
        "tags": [],
    }
    job_id = uuid.uuid4().hex[:10]
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir()
    src = None
    f = request.files.get("video")
    name = "Your vlog"
    if f and f.filename:
        ext = Path(f.filename).suffix.lower() or ".mp4"
        src = job_dir / f"source{ext}"
        f.save(src)
        name = Path(f.filename).stem
    elif not link:
        return jsonify(error="Add a video file or a Google Drive link."), 400
    with LOCK:
        JOBS[job_id] = {"id": job_id, "status": "working", "stage": 0, "pct": 0, "msg": "",
                        "count": count, "style": style, "schedule": schedule, "name": name,
                        "stages": STAGES, "shorts": [], "vlog": vlog}
    threading.Thread(target=make_shorts, args=(job_id, src, link, count, style, vlog), daemon=True).start()
    return jsonify(id=job_id)


@app.get("/api/status/<job_id>")
def status(job_id):
    with LOCK:
        job = JOBS.get(job_id)
        if not job and re.fullmatch(r"[0-9a-f]{10}", job_id):
            saved = JOBS_DIR / job_id / "job.json"
            if saved.exists():  # app was restarted: reload finished jobs
                job = json.loads(saved.read_text(encoding="utf-8"))
                if job.get("status") == "working":
                    job.update(status="error", error="Clipline was closed while this was running. Start it again.")
                if job.get("upload_status") in ("starting", "connecting", "uploading"):
                    job.update(upload_status="error", upload_msg="Clipline was closed during posting.")
                JOBS[job_id] = job
        if not job:
            abort(404)
        return jsonify(job)


@app.get("/media/<job_id>/<path:name>")
def media(job_id, name):
    if not re.fullmatch(r"[0-9a-f]{10}", job_id) or not re.fullmatch(r"(short|thumb)_\d+\.(mp4|jpg)", name):
        abort(404)
    return send_from_directory(JOBS_DIR / job_id, name, conditional=True)


# --------------------------------------------------------------------------- schedule & upload
def do_upload(job_id, items, mode):
    job_dir = JOBS_DIR / job_id
    results = []
    try:
        update(job_id, upload_status="connecting", upload_msg="Connecting to YouTube (approve in the browser tab)")
        service = yt.get_service()
        times = yt.plan_times(len(items), mode)
        for k, (it, when) in enumerate(zip(items, times)):
            label = f"Uploading Short {k + 1} of {len(items)}"
            update(job_id, upload_status="uploading", upload_msg=label, upload_pct=0)
            tags = it.get("hashtags", [])
            desc = (it.get("hook", "") + "\n\n" + " ".join("#" + t for t in tags + ["Shorts"])).strip()
            title = it["title"]
            if "#shorts" not in title.lower() and len(title) <= 90:
                title += " #Shorts"
            vid, note = yt.upload_short(
                service, job_dir / it["video"], title, desc, tags, when, job_dir / it["thumb"],
                progress=lambda p: update(job_id, upload_pct=p),
            )
            results.append({"idx": it["idx"], "title": it["title"], "video_id": vid,
                            "when": when.isoformat() if when else None, "note": note})
            update(job_id, uploads=results)
        update(job_id, upload_status="done", upload_msg="All scheduled", uploads=results)
    except Exception as e:
        traceback.print_exc()
        update(job_id, upload_status="error", upload_msg=str(e), uploads=results)


@app.post("/api/schedule/<job_id>")
def schedule(job_id):
    data = request.get_json(force=True)
    with LOCK:
        job = JOBS.get(job_id)
        if not job or job.get("status") != "ready":
            abort(400)
        by_idx = {s["idx"]: s for s in job["shorts"]}
    if not yt.is_configured():
        return jsonify(error="YouTube isn't connected yet: client_secret.json is missing. "
                             "The Shorts are saved in the jobs folder, so you can post them by hand, "
                             "or follow README step 5 to turn on automatic posting."), 400
    items = []
    for row in data.get("shorts", []):
        s = by_idx.get(int(row["idx"]))
        if s and row.get("keep"):
            items.append({**s, "title": (row.get("title") or s["title"]).strip()[:95]})
    if not items:
        return jsonify(error="Tick at least one Short."), 400
    mode = data.get("schedule", job.get("schedule", "d18"))
    update(job_id, upload_status="starting", uploads=[], schedule=mode)
    threading.Thread(target=do_upload, args=(job_id, items, mode), daemon=True).start()
    return jsonify(ok=True)


@app.get("/api/vlog-info")
def vlog_info():
    try:
        return jsonify(yt.fetch_video_info(request.args.get("url", "")))
    except RuntimeError as e:
        return jsonify(error=str(e)), 400


@app.get("/api/config")
def config():
    return jsonify(youtube=yt.is_configured(), today=date.today().isoformat())


@app.get("/")
def index():
    return send_from_directory(ROOT / "static", "index.html")


if __name__ == "__main__":
    url = "http://localhost:8000"
    print(f"\n  Clipline is running at {url}\n  Keep this window open while you use it.\n")
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=8000, debug=False, threaded=True)
