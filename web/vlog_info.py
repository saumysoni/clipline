"""
Reading a vlog's title and description from its YouTube link, for the setup form.
"""
from flask import jsonify, request

import youtube as yt

from web.server import app


@app.get("/api/vlog-info")
def vlog_info():
    try:
        return jsonify(yt.fetch_video_info(request.args.get("url", "")))
    except RuntimeError as e:
        return jsonify(error=str(e)), 400
