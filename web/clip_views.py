"""
Views on the Shorts & Reels cards (js/clips.js asks after the cards are drawn, so they never wait for it): each posted
clip's views so far on YouTube (live count, what Studio shows) and Instagram (the Reel's lifetime views). Both are
cached 10 minutes by their helpers. Trouble on one platform leaves its numbers out; the cards then show no count.
"""
import traceback

from flask import g, jsonify

import youtube as yt
from instagram.insights import reel_numbers
from youtube.analytics_more import live_views

from web.analytics_clips import posted_clips
from web.server import app


@app.get("/api/clips/views")
def clip_views():
    uid = g.user["id"]
    clips = posted_clips(uid)
    yt_ids = [c["youtube"]["video_id"] for c in clips if c["youtube"]]
    posts = [{"media_id": c["instagram"]["media_id"], "ig_id": c["instagram"]["ig_id"]} for c in clips if c["instagram"]]
    ytv, igv = {}, {}
    if yt_ids:
        try:
            if yt.account(uid)["signed_in"]:
                ytv = live_views(uid, yt_ids)
        except Exception:  # noqa: BLE001  (YouTube trouble shouldn't hide Instagram numbers)
            traceback.print_exc()
    if posts:
        try:
            igv = {mid: row.get("views", 0) for mid, row in reel_numbers(uid, posts).items()}
        except Exception:  # noqa: BLE001
            traceback.print_exc()
    out = {}
    for c in clips:
        y = ytv.get(c["youtube"]["video_id"]) if c["youtube"] else None
        i = igv.get(c["instagram"]["media_id"]) if c["instagram"] else None
        if y is not None or i is not None:
            out[f'{c["job"]}:{c["idx"]}'] = {"youtube": y, "instagram": i}
    return jsonify(views=out)
