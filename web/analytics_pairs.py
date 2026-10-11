"""
Analytics, Videos tab: each Pit Crew clip on YouTube and on Instagram side by side (views, likes, comments,
shares, new subscribers vs new followers, % viewed / watch time), since each clip was posted.

YouTube: live views/likes/comments + Analytics shares/subscribers (youtube.analytics_more.clip_totals).
Instagram: each Reel's lifetime numbers (instagram.insights.reel_numbers). Instagram doesn't say which Reel brought a
follower, so "new followers" is the account's new followers in the 2 days after the Reel went out
(instagram.account_insights.follows_after), and the page says so.
"""
import re
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from flask import g, jsonify, request

import youtube as yt
from instagram.account_insights import follows_after
from instagram.insights import reel_numbers
from youtube.analytics_more import clip_totals

from web.analytics_clips import posted_clips
from web.server import app

FOLLOW_HOURS = 48


def clip_pairs(user_id, vlog=""):
    """Every posted clip (newest first) with its YouTube and Instagram numbers."""
    clips = posted_clips(user_id, vlog)
    yt_ids = [c["youtube"]["video_id"] for c in clips if c["youtube"]]
    posts = [{"media_id": c["instagram"]["media_id"], "ig_id": c["instagram"]["ig_id"]} for c in clips if c["instagram"]]
    ytn, ign, notes = {}, {}, []
    if yt_ids:
        try:
            if yt.account(user_id)["signed_in"]:
                ytn = clip_totals(user_id, yt_ids)
        except Exception:  # noqa: BLE001  (YouTube trouble shouldn't hide Instagram numbers)
            traceback.print_exc()
            notes.append("youtube")
    if posts:
        try:
            ign = reel_numbers(user_id, posts)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            notes.append("instagram")

    def follows(c):
        i = c["instagram"]
        if not i or not i.get("at"):
            return None
        try:
            return follows_after(user_id, i["ig_id"], datetime.fromisoformat(i["at"]), FOLLOW_HOURS)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            return None
    with ThreadPoolExecutor(4) as ex:
        fol = list(ex.map(follows, clips))
    out = []
    for c, f in zip(clips, fol):
        y = ytn.get(c["youtube"]["video_id"]) if c["youtube"] else None
        i = ign.get(c["instagram"]["media_id"]) if c["instagram"] else None
        row = {"job": c["job"], "idx": c["idx"], "title": c["title"], "vlog": c["vlog"], "thumb": c["thumb"],
               "length": c["length"], "posted_at": c["posted_at"], "youtube": None, "instagram": None}
        if c["youtube"]:
            row["youtube"] = {"video_id": c["youtube"]["video_id"], "channel": c["youtube"]["channel"],
                              "at": c["youtube"]["at"], **({k: y.get(k) for k in ("views", "likes", "comments", "shares", "subs",
                                                                                     "engaged", "avg_pct", "avg_secs", "thumb")} if y else {})}
        if c["instagram"]:
            row["instagram"] = {"media_id": c["instagram"]["media_id"], "permalink": c["instagram"]["permalink"],
                                "username": c["instagram"]["username"], "at": c["instagram"]["at"],
                                **({"views": i.get("views", 0), "reach": i.get("reach", 0), "likes": i.get("likes", 0),
                                    "comments": i.get("comments", 0), "shares": i.get("shares", 0), "saved": i.get("saved", 0),
                                    "avg_watch_s": i.get("avg_watch_s")} if i else {}),
                                "follows": f["follows"] if f else None, "follows_complete": bool(f and f["complete"])}
        out.append(row)
    out.sort(key=lambda r: r["posted_at"] or "", reverse=True)
    return {"clips": out, "follow_hours": FOLLOW_HOURS, "problems": notes}


@app.get("/api/analytics/pairs")
def analytics_pairs():
    vlog = request.args.get("vlog", "")
    vlog = vlog if re.fullmatch(r"[0-9a-f]{10}", vlog) else ""
    try:
        return jsonify(clip_pairs(g.user["id"], vlog))
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return jsonify(error="Couldn't load your clips' numbers right now. Try Refresh in a minute."), 502
