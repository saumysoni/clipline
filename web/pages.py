"""
The page itself, finished files (Shorts, thumbnails, preview) and basic config.
"""
import os
import re
from datetime import date

from flask import Response, abort, jsonify, request, send_from_directory

import pipeline
import youtube as yt
from settings import JOBS_DIR, ROOT

from web.server import app


@app.get("/media/<job_id>/<path:name>")
def media(job_id, name):
    if not re.fullmatch(r"[0-9a-f]{10}", job_id) or not re.fullmatch(r"(short|thumb)_\d+\.(mp4|jpg)|preview\.mp4|poster\.jpg|vthumb_\d+\.jpg|source\.[a-z0-9]{2,4}", name):
        abort(404)
    if request.args.get("cover") == "1" and name.startswith("short_"):  # Save: with the thumbnail first
        thumb = request.args.get("thumb", "")
        if re.fullmatch(r"thumb_\d+\.jpg", thumb) and (JOBS_DIR / job_id / thumb).exists():
            try:
                name = pipeline.covered_video(JOBS_DIR / job_id, name, thumb).name
            except Exception as e:  # noqa: BLE001  (fall back to the plain Short)
                print("Couldn't add the thumbnail as the first frame:", repr(e)[:300])
    dl = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "", request.args.get("dl", "")).strip()[:80]
    if dl:  # a download button: save it under a readable name (e.g. "Rainy taxi - thumbnail.jpg")
        ext = name.rsplit(".", 1)[1]
        dl = dl if dl.lower().endswith("." + ext) else f"{dl}.{ext}"
        return send_from_directory(JOBS_DIR / job_id, name, conditional=True, as_attachment=True, download_name=dl)
    return send_from_directory(JOBS_DIR / job_id, name, conditional=True)


@app.get("/api/config")
def config():
    from web.allowance import longest  # (public: settings everyone sees, nothing about the visitor)
    return jsonify(youtube=yt.is_configured(), today=date.today().isoformat(),  # sign-in: /api/youtube/me
                   support=os.getenv("SUPPORT_EMAIL", "").strip(), longest=longest())


INCLUDE = re.compile(r"<!-- include (sections/[\w-]+\.html) -->")


@app.get("/")
def index():
    """static/index.html with each <!-- include sections/x.html --> replaced by that file (one file per screen)."""
    static = ROOT / "static"
    page = INCLUDE.sub(lambda m: (static / m.group(1)).read_text(encoding="utf-8").rstrip("\n"),
                       (static / "index.html").read_text(encoding="utf-8"))
    return Response(page, mimetype="text/html", headers={"Cache-Control": "no-cache"})
