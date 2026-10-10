"""
Sending a vlog's video in pieces, so a dropped connection (or a closed tab) doesn't mean starting again from zero.

  1. POST /api/upload/new {name, size}            -> {id, received: 0}   (refused if too big or no room)
  2. POST /api/upload/<id>?offset=N  (raw bytes)   -> {received}          (pieces of PIECE_MB, one after another)
  3. GET  /api/upload/<id>                         -> {received, size}    (after a failure: where to carry on)
  4. /api/start or /api/vlog/start with upload=<id> -> take_upload() moves the finished file into the vlog's folder.

The server's count of received bytes is the only truth: a piece at an earlier offset is a repeat (nothing is written),
one past it is refused (409, with the count), so a retry can never leave a gap or a doubled piece. One lock per upload,
so two tabs can't interleave. An upload a start route refused (a bad link, a bad time) stays, so the creator can fix
the field and press the button again without sending the video again. Unfinished uploads go after STALE_HOURS.

Cloud: the pieces sit on this server's disk (jobs/_uploads), so one process (like the queue). With file storage, swap
this for its own resumable uploads; the page only needs sendVideo(file) -> upload id (js/video-upload.js).
"""
import json
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

from flask import abort, g, jsonify, request

from settings import JOBS_DIR

from web.allowance import problem
from web.server import app


UPLOADS_DIR = JOBS_DIR / "_uploads"
PIECE_MB = 8  # js/video-upload.js sends pieces of this size; the server takes up to 4x (web/server.py)
STALE_HOURS = 24
SPARE_GB = 2  # room left over for the Shorts, thumbnails and everything else


def max_bytes():
    try:
        return max(0.1, float(os.getenv("MAX_UPLOAD_GB", "30"))) * 1e9
    except ValueError:
        return 30e9


LOCKS = {}  # upload id -> its lock
_LOCKS_LOCK = threading.Lock()


def _lock(upload_id):
    with _LOCKS_LOCK:
        return LOCKS.setdefault(upload_id, threading.Lock())


def _dir(upload_id):
    if not re.fullmatch(r"[0-9a-f]{32}", upload_id or ""):
        return None
    return UPLOADS_DIR / upload_id


def _meta(upload_id):
    d = _dir(upload_id)
    try:
        return json.loads((d / "meta.json").read_text(encoding="utf-8")) if d else None
    except (OSError, ValueError):
        return None


def _received(upload_id):
    try:
        return (UPLOADS_DIR / upload_id / "data").stat().st_size
    except OSError:
        return 0


def _mine(upload_id):
    """This creator's upload (meta), or 404."""
    meta = _meta(upload_id)
    if not meta or meta.get("owner") != g.user["id"]:
        abort(404)
    return meta


def _clean_stale():
    now = time.time()
    for d in UPLOADS_DIR.glob("*"):
        meta = _meta(d.name)
        if not meta or now - meta.get("touched", meta.get("created", 0)) > STALE_HOURS * 3600:
            shutil.rmtree(d, ignore_errors=True)
            LOCKS.pop(d.name, None)


def _still_needed():
    """Bytes that unfinished uploads will still write (so ten big uploads can't all be let in at once)."""
    total = 0
    for d in UPLOADS_DIR.glob("*"):
        meta = _meta(d.name)
        if meta:
            total += max(0, meta["size"] - _received(d.name))
    return total


@app.post("/api/upload/new")
def upload_new():
    data = request.get_json(force=True)
    name = Path(str(data.get("name") or "video.mp4")).name[:200]
    try:
        size = int(data.get("size") or 0)
    except (TypeError, ValueError):
        size = 0
    if size <= 0:
        return jsonify(error="That file is empty. Choose your vlog's video file."), 400
    why = problem(g.user["id"])  # this month's allowance used up: say so before gigabytes are sent
    if why:
        return jsonify(error=why), 403
    if size > max_bytes():
        return jsonify(error=f"That video is {size / 1e9:.1f} GB; Pit Crew takes videos up to "
                             f"{max_bytes() / 1e9:.0f} GB. Export a smaller file (1080p is plenty for Shorts)."), 400
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    _clean_stale()
    free = shutil.disk_usage(UPLOADS_DIR).free
    if free - _still_needed() < size + SPARE_GB * 1e9:
        print(f"No room for a {size / 1e9:.1f} GB upload: {free / 1e9:.1f} GB free, "
              f"{_still_needed() / 1e9:.1f} GB promised to unfinished uploads.")
        return jsonify(error="Pit Crew doesn't have room for this video right now. Try again later; if it keeps "
                             "happening, tell us."), 503
    upload_id = uuid.uuid4().hex
    d = UPLOADS_DIR / upload_id
    d.mkdir()
    (d / "data").touch()
    now = time.time()
    (d / "meta.json").write_text(json.dumps({"owner": g.user["id"], "name": name, "size": size, "created": now,
                                             "touched": now}), encoding="utf-8")
    return jsonify(id=upload_id, received=0)


@app.get("/api/upload/<upload_id>")
def upload_status(upload_id):
    meta = _mine(upload_id)
    return jsonify(received=_received(upload_id), size=meta["size"])


@app.post("/api/upload/<upload_id>")
def upload_piece(upload_id):
    meta = _mine(upload_id)
    try:
        offset = int(request.args.get("offset", "-1"))
    except ValueError:
        offset = -1
    with _lock(upload_id):
        have = _received(upload_id)
        if offset < have:  # a repeat of a piece that already arrived
            return jsonify(received=have)
        if offset > have:  # a gap: the page asks for the count and carries on from there
            return jsonify(received=have, error="A piece went missing."), 409
        left = meta["size"] - have
        with open(UPLOADS_DIR / upload_id / "data", "ab") as f:
            while True:
                piece = request.stream.read(1 << 20)
                if not piece:
                    break
                if len(piece) > left:
                    f.write(piece[:left])
                    break
                f.write(piece)
                left -= len(piece)
        meta["touched"] = time.time()
        (UPLOADS_DIR / upload_id / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        return jsonify(received=_received(upload_id))


def finished_upload(upload_id, owner):
    """The file of a finished upload of this creator's, or None."""
    meta = _meta(upload_id)
    if not meta or meta.get("owner") != owner or _received(upload_id) != meta["size"]:
        return None
    return UPLOADS_DIR / upload_id / "data"


def discard_upload(upload_id):
    if _dir(upload_id):
        with _lock(upload_id):
            shutil.rmtree(UPLOADS_DIR / upload_id, ignore_errors=True)
        LOCKS.pop(upload_id, None)


def take_upload(upload_id, owner, job_dir):
    """Move a finished upload into a vlog's folder as source.<ext>. Returns (path, the file's name without extension).
    Raises RuntimeError in plain words. Call only once the start request has passed every other check."""
    meta = _meta(upload_id)
    if not meta or meta.get("owner") != owner:
        raise RuntimeError("Pit Crew doesn't have that video any more. Choose the file again.")
    with _lock(upload_id):
        if _received(upload_id) != meta["size"]:
            raise RuntimeError("The video hasn't finished sending. Press the button again to carry on.")
        ext = Path(meta["name"]).suffix.lower()
        src = job_dir / f"source{ext if re.fullmatch(r'[.][a-z0-9]{1,5}', ext) else '.mp4'}"
        shutil.move(str(UPLOADS_DIR / upload_id / "data"), src)
        shutil.rmtree(UPLOADS_DIR / upload_id, ignore_errors=True)
    LOCKS.pop(upload_id, None)
    return src, Path(meta["name"]).stem
