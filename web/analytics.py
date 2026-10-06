"""
Analytics page: how the creator's Shorts are doing (YouTube now; Instagram once connected).
The numbers come from youtube/analytics.py; this file only serves them to the page.
"""
import re
import traceback

from flask import g, jsonify, request

import instagram as ig
import youtube as yt

from web.instagram_posting import clipline_reel_ids
from web.on_youtube import posted_shorts
from web.server import app


def _days():
    try:
        d = int(request.args.get("days", 28))
    except ValueError:
        d = 28
    return d if d in (0, 7, 28, 90, 365) else 28


def _plain(e):
    """A plain sentence for an analytics problem (upload_error_message talks about uploads)."""
    from googleapiclient.errors import HttpError

    if isinstance(e, HttpError):
        print("YouTube Analytics error:", e.resp.status, (e.content or b"")[:400])
        if e.resp.status in (429, 500, 503):
            return "YouTube Analytics is busy right now. Try again in a few minutes."
        return "YouTube Analytics couldn't give these numbers right now. Try again in a few minutes."
    return yt.upload_error_message(e)


@app.get("/api/analytics")
def analytics():
    uid = g.user["id"]
    out = {"connected": False, "instagram_state": _instagram_state(uid)}
    if out["instagram_state"].get("can_post"):  # personal accounts have no insights: the page shows the switch steps
        try:
            out["instagram"] = ig.dashboard(uid, clipline_reel_ids(uid))
        except ig.InstagramError as e:
            out["instagram_error"] = str(e)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            out["instagram_error"] = "Couldn't load your Instagram numbers. Try Refresh."
    if not yt.account(uid)["signed_in"]:
        return jsonify(out)
    out["connected"] = True
    try:
        ids = [u["video_id"] for u in posted_shorts(uid) if u.get("video_id")]
        out["youtube"] = yt.analytics_dashboard(uid, _days(), ids)
        return jsonify(out)
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        out["error"] = _plain(e)
        return jsonify(out), 502


def _instagram_state(uid):
    try:
        return ig.account(uid)
    except ig.InstagramError:
        return {"configured": True, "signed_in": True, "offline": True}


@app.get("/api/analytics/short/<video_id>")
def analytics_short(video_id):
    if not video_id.replace("-", "").replace("_", "").isalnum() or len(video_id) > 20:
        return jsonify(error="That isn't a YouTube video."), 400
    try:
        channel = request.args.get("channel") or None  # the channel it went up on (several can be connected)
        if channel and not re.fullmatch(r"UC[\w-]{22}", channel):
            channel = None
        return jsonify(yt.analytics_short(g.user["id"], video_id, channel=channel))
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        return jsonify(error=_plain(e)), 502
