"""
Analytics page: how the creator's Shorts are doing (YouTube now; Instagram once connected).
The numbers come from youtube/analytics.py; this file only serves them to the page.
"""
import traceback

from flask import g, jsonify, request

import youtube as yt

from web.on_youtube import posted_shorts
from web.server import app


def _days():
    try:
        d = int(request.args.get("days", 28))
    except ValueError:
        d = 28
    return d if d in (0, 7, 28, 90, 365) else 28


@app.get("/api/analytics")
def analytics():
    uid = g.user["id"]
    acct = yt.account(uid)
    if not acct["signed_in"]:
        return jsonify(connected=False)
    try:
        ids = [u["video_id"] for u in posted_shorts(uid) if u.get("video_id")]
        data = yt.analytics_dashboard(uid, _days(), ids)
        return jsonify(connected=True, youtube=data)
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        return jsonify(connected=True, error=yt.upload_error_message(e)), 502


@app.get("/api/analytics/short/<video_id>")
def analytics_short(video_id):
    if not video_id.replace("-", "").replace("_", "").isalnum() or len(video_id) > 20:
        return jsonify(error="That isn't a YouTube video."), 400
    try:
        return jsonify(yt.analytics_short(g.user["id"], video_id, _days()))
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        return jsonify(error=yt.upload_error_message(e)), 502
