"""
Clipline: run `python app.py`, then open http://localhost:8000
"""
import hashlib
import json
import logging
import re
import shutil
import sys
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
sys.stdout.reconfigure(line_buffering=True)  # log lines appear at once, also when written to a file

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
        vlog = dict(vlog or {})
        if vlog.get("youtube_url") and not (vlog.get("title") and vlog.get("description")):
            try:  # the page normally fills these in already; this covers a skipped lookup
                info = yt.fetch_video_info(vlog["youtube_url"])
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
        # All the editing first, then all the thumbnails, so the steps on the page only move forward.
        rendered = []
        for i, m in enumerate(moments, 1):
            update(job_id, stage=3, pct=(i - 1) / len(moments) * 100,
                   msg=f"Editing Short {i} of {len(moments)}")
            rendered.append(pipeline.render_short(src, meta, m, tr["words"], i, style, job_dir))
        shorts = []
        for i, (m, (video, cx)) in enumerate(zip(moments, rendered), 1):
            update(job_id, stage=4, pct=(i - 1) / len(moments) * 100,
                   msg=f"Thumbnail {i} of {len(moments)}")
            thumb = pipeline.make_thumbnail(src, meta, m, cx, i, job_dir, tr["words"], vlog)
            shorts.append({**m, "idx": i, "video": video, "thumb": thumb, "keep": True, "cx": cx})
            update(job_id, shorts=shorts)
        update(job_id, stage=5, pct=100, msg="Done", status="ready", shorts=shorts)
        start_preview(job_id)  # ready by the time the creator wants to choose a scene on the video
    except Exception as e:
        traceback.print_exc()
        update(job_id, status="error", error=str(e))


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
        JOBS[job_id] = {"id": job_id, "status": "working", "stage": 0, "pct": 0, "msg": "",
                        "count": count, "style": style, "schedule": schedule, "name": name,
                        "stages": STAGES, "shorts": [], "vlog": vlog, "note": note,
                        "must": [{"start": a, "end": b} for a, b in must]}
    threading.Thread(target=make_shorts, args=(job_id, src, link, count, style, vlog, note, must),
                     daemon=True).start()
    return jsonify(id=job_id)


def load_job(job_id):
    """The job from memory, or from its job.json if the app was restarted. Call with LOCK held."""
    job = JOBS.get(job_id)
    if not job and re.fullmatch(r"[0-9a-f]{10}", job_id):
        saved = JOBS_DIR / job_id / "job.json"
        if saved.exists():  # app was restarted: reload finished jobs
            job = json.loads(saved.read_text(encoding="utf-8"))
            if job.get("status") == "working":
                job.update(status="error", error="Clipline was closed while this was running. Start it again.")
            if job.get("upload_status") in ("starting", "connecting", "uploading"):
                job.update(upload_status="error", upload_msg="Clipline was closed during posting.")
            job["shorts"] = [s for s in job.get("shorts", []) if not s.get("pending")]
            for s in job["shorts"]:
                if s.pop("retrying", None):
                    s["retry_error"] = "Clipline was closed while this was being remade. Try again."
            JOBS[job_id] = job
    return job


@app.get("/api/status/<job_id>")
def status(job_id):
    with LOCK:
        job = load_job(job_id)
        if not job:
            abort(404)
        return jsonify(job)


@app.get("/media/<job_id>/<path:name>")
def media(job_id, name):
    if not re.fullmatch(r"[0-9a-f]{10}", job_id) or not re.fullmatch(r"(short|thumb)_\d+\.(mp4|jpg)|preview\.mp4", name):
        abort(404)
    return send_from_directory(JOBS_DIR / job_id, name, conditional=True)


# --------------------------------------------------------------------------- preview for choosing scenes
PREVIEWS = {}  # job id -> "building" or an error message, while or after making preview.mp4


def build_preview(job_id):
    job_dir = JOBS_DIR / job_id
    try:
        src = next(job_dir.glob("source.*"), None)
        if not src:
            raise RuntimeError("The original video for this job is gone, so it can't be shown. "
                               "Start a new vlog instead.")
        pipeline.make_preview(src, job_dir / "preview.mp4")
        with LOCK:
            PREVIEWS.pop(job_id, None)
    except Exception as e:
        traceback.print_exc()
        msg = str(e) if isinstance(e, RuntimeError) and not str(e).startswith("Command failed") else \
            "Couldn't prepare the video for choosing a scene. You can still type the From and To times."
        with LOCK:
            PREVIEWS[job_id] = msg


def start_preview(job_id):
    """Make preview.mp4 in the background unless it exists or is being made. Returns its state."""
    if (JOBS_DIR / job_id / "preview.mp4").exists():
        return "ready"
    with LOCK:
        state = PREVIEWS.get(job_id)
        if state == "building":
            return "building"
        PREVIEWS[job_id] = "building"
    threading.Thread(target=build_preview, args=(job_id,), daemon=True).start()
    return "building"


@app.post("/api/preview/<job_id>")
def preview(job_id):
    """Start making the preview if needed; the page calls this again until it's ready."""
    with LOCK:
        job = load_job(job_id)
        failed = PREVIEWS.get(job_id) not in (None, "building")
    if not job:
        abort(404)
    if failed and not (request.get_json(silent=True) or {}).get("retry"):
        return jsonify(status="error", error=PREVIEWS[job_id])
    state = start_preview(job_id)
    return jsonify(status=state, url=f"/media/{job_id}/preview.mp4" if state == "ready" else None)


# --------------------------------------------------------------------------- try again
RETRY_LOCKS = {}  # one remake at a time per job, so two new picks can't land on the same moment


def update_short(job_id, idx, **kw):
    with LOCK:
        job = JOBS[job_id]
        job["shorts"] = [{**s, **kw} if s["idx"] == idx else s for s in job["shorts"]]
        (JOBS_DIR / job_id / "job.json").write_text(json.dumps(job, default=str), encoding="utf-8")


def read_times(start, end, label="the moment"):
    """(start, end) in seconds from what the creator typed, None if both are empty.
    Raises RuntimeError with a plain message if they don't make sense."""
    start, end = str(start or "").strip(), str(end or "").strip()
    if not start and not end:
        return None
    s, e = pipeline.parse_time(start), pipeline.parse_time(end)
    if s is None or e is None:
        raise RuntimeError(f"Type both times for {label} like 2:10 (minutes:seconds), for example From 2:10 To 2:45.")
    if e <= s:
        raise RuntimeError(f"For {label}, the To time has to be after the From time.")
    return s, e


def next_file_number(job):
    """A file number no Short uses yet, so the browser shows a new file instead of a cached old one."""
    used = [int(n) for s in job["shorts"] for n in re.findall(r"_(\d+)\.", s["video"] + s["thumb"])]
    return max(used + [len(job["shorts"])]) + 1


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
                raise RuntimeError("The original video for this job is gone, so it can't be remade. "
                                   "Start a new vlog instead.")
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
            job["shorts"] = [{**m, "idx": idx, "video": video, "thumb": thumb, "keep": True, "tried": rejected, "cx": cx}
                             if s["idx"] == idx else s for s in job["shorts"]]
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


def editable_job(job_id):
    """The job if Shorts can be remade or added now, else an error response. Call with LOCK held."""
    job = load_job(job_id)
    if not job or job.get("status") != "ready":
        abort(400)
    if job.get("upload_status") in ("starting", "connecting", "uploading"):
        return None, (jsonify(error="Wait until posting has finished."), 400)
    return job, None


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


@app.post("/api/add/<job_id>")
def add_short(job_id):
    """A Short for a moment the AI missed: described in words, or the creator's own times."""
    data = request.get_json(silent=True) or {}
    note = str(data.get("note", ""))[:500]
    try:
        times = read_times(data.get("start"), data.get("end"))
    except RuntimeError as e:
        return jsonify(error=str(e)), 400
    if not times and not note.strip():
        return jsonify(error="Describe the moment you want, or type its From and To times."), 400
    with LOCK:
        job, problem = editable_job(job_id)
        if problem:
            return problem
        if len(job["shorts"]) >= 20:
            return jsonify(error="That's the most Shorts one vlog can have here (20)."), 400
        idx = max([s["idx"] for s in job["shorts"]] + [0]) + 1
        job["shorts"].append({"idx": idx, "pending": True, "retrying": True, "retry_msg": "Waiting for the other Short to finish",
                              "start": 0, "end": 0, "title": "", "why": "", "video": "", "thumb": "", "keep": True})
        job["add_error"] = None
        if job.get("upload_status") == "error":
            job["upload_status"] = None
        (JOBS_DIR / job_id / "job.json").write_text(json.dumps(job, default=str), encoding="utf-8")
    threading.Thread(target=remake_short, args=(job_id, idx, note, times), daemon=True).start()
    return jsonify(ok=True, idx=idx)


# --------------------------------------------------------------------------- hooks
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
                raise RuntimeError("The original video for this job is gone, so the hook can't be changed. "
                                   "Start a new vlog instead.")
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
            lead = it.get("hook", "") if it.get("hook_mode", "text") != "none" else it.get("title", "")
            desc = (lead + "\n\n" + " ".join("#" + t for t in tags + ["Shorts"])).strip()
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
        job = load_job(job_id)
        if not job or job.get("status") != "ready":
            abort(400)
        by_idx = {s["idx"]: s for s in job["shorts"]}
        if any(s.get("retrying") for s in job["shorts"]):
            return jsonify(error="Wait until the Short you're remaking is ready."), 400
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
