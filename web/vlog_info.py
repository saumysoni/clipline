"""
Reading a vlog's title and description from its YouTube link, for the setup form.
"""
from flask import g, jsonify, request

import youtube as yt

from web.server import app


@app.get("/api/vlog-info")
def vlog_info():
    try:
        # the creator's YouTube connection (if any) lets Pit Crew read the description without an API key
        return jsonify(yt.fetch_video_info(request.args.get("url", ""), yt.access_token(g.user["id"])))
    except RuntimeError as e:
        return jsonify(error=str(e)), 400
