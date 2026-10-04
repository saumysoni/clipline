"""
The page itself, finished files (Shorts, thumbnails, preview) and basic config.
"""
import re
from datetime import date

from flask import Response, abort, jsonify, request, send_from_directory

import youtube as yt
from settings import JOBS_DIR, ROOT

from web.server import app


@app.get("/media/<job_id>/<path:name>")
def media(job_id, name):
    if not re.fullmatch(r"[0-9a-f]{10}", job_id) or not re.fullmatch(r"(short|thumb)_\d+\.(mp4|jpg)|preview\.mp4", name):
        abort(404)
    dl = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "", request.args.get("dl", "")).strip()[:80]
    if dl:  # a download button: save it under a readable name (e.g. "Rainy taxi - thumbnail.jpg")
        ext = name.rsplit(".", 1)[1]
        dl = dl if dl.lower().endswith("." + ext) else f"{dl}.{ext}"
        return send_from_directory(JOBS_DIR / job_id, name, conditional=True, as_attachment=True, download_name=dl)
    return send_from_directory(JOBS_DIR / job_id, name, conditional=True)


@app.get("/api/config")
def config():
    return jsonify(youtube=yt.is_configured(), today=date.today().isoformat())  # sign-in: /api/youtube/me


INCLUDE = re.compile(r"<!-- include (sections/[\w-]+\.html) -->")


@app.get("/")
def index():
    """static/index.html with each <!-- include sections/x.html --> replaced by that file (one file per screen)."""
    static = ROOT / "static"
    page = INCLUDE.sub(lambda m: (static / m.group(1)).read_text(encoding="utf-8").rstrip("\n"),
                       (static / "index.html").read_text(encoding="utf-8"))
    return Response(page, mimetype="text/html", headers={"Cache-Control": "no-cache"})
