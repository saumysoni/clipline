"""
Everything on the creator's YouTube channels that Pit Crew didn't post (youtube/channel_videos.py): long videos show on the Videos
page, Shorts on Shorts & Reels, with a YouTube link and the reason Pit Crew can't work on them. What Pit Crew posted is
already there from its own records, so it's left out here.

Read from YouTube at most once a day per channel (the daily upkeep, or when the page opens and the list is older): a few
titles are kept so the pages open at once and a video that's gone can show as "Removed or deleted from YouTube". That card
keeps only the title, for GONE_DAYS, and no picture (YouTube Developer Policies III.E.4: web/youtube_upkeep.py, gotcha 27).
"""
import re
import threading
import time
import traceback

from flask import g, jsonify

import youtube as yt
from accounts import db

from web.server import app
from web.vlogs import user_jobs

DAY = 24 * 3600
GONE_DAYS = 30
CHECK_NOW_EVERY = 6 * 3600  # Check now works this often (seconds): YouTube's quota is shared by all creators (about 21 units a check)
_RUNNING, _ASKED = set(), {}


def _own_ids(user_id):
    """Every video id Pit Crew posted for this creator: those have their own records and cards."""
    ids = set()
    for job in user_jobs(user_id):
        ids.add((job.get("vpost") or {}).get("video_id"))
        ids |= {u.get("video_id") for u in job.get("uploads") or []}
    return ids - {None, ""}


def refresh_channel(user_id, channel, now=None):
    """Read one channel's list and note what's gone. Any YouTube error changes nothing."""
    now = now or time.time()
    try:
        service = yt.get_service(user_id, channel)
        rows = yt.channel_videos(service)
        own = _own_ids(user_id)
        rows = [r for r in rows if r["id"] not in own]
        listed = {r["id"] for r in rows}
        missing = [v for v in db.channel_video_ids(user_id, channel) if v not in listed]
        # Not on the list isn't proof: the list stops at the newest videos, and one may have gone private.
        states = yt.video_states(service, missing) if missing else {}
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return False
    db.save_channel_videos(user_id, channel, rows, now)
    for vid in missing:
        state = states.get(vid)
        if state is None:
            db.channel_video_gone(user_id, vid, now)
        elif state.get("privacy") not in ("public", "unlisted"):
            db.channel_video_remove(user_id, vid)  # private now: not "posted" any more, and YouTube still has it
    db.set_channel_checked(user_id, channel, now)
    return True


def refresh_user(user_id, now=None):
    now = now or time.time()
    for row in db.connections(user_id, "youtube"):
        if row["account_id"]:
            refresh_channel(user_id, row["account_id"], now)
    db.forget_old_channel_videos(user_id, now - GONE_DAYS * DAY)


def _soon(user_id):
    if user_id in _RUNNING:
        return

    def run():
        try:
            refresh_user(user_id)
        finally:
            _RUNNING.discard(user_id)
    _RUNNING.add(user_id)
    threading.Thread(target=run, daemon=True).start()


def items_for(user_id):
    own, out = _own_ids(user_id), []
    for r in db.channel_video_rows(user_id):
        if r["video_id"] in own:
            continue
        gone = r["gone_at"] is not None
        out.append({"id": r["video_id"], "title": r["title"], "published": r["published"], "seconds": r["seconds"],
                    "short": bool(r["is_short"]), "privacy": r["privacy"], "gone": gone,
                    "url": "" if gone else ("https://www.youtube.com/shorts/" if r["is_short"] else "https://www.youtube.com/watch?v=") + r["video_id"],
                    "thumb": "" if gone else f"https://i.ytimg.com/vi/{r['video_id']}/mqdefault.jpg"})
    return out


@app.get("/api/channel-videos")
def channel_video_list():
    uid, now = g.user["id"], time.time()
    channels = [r["account_id"] for r in db.connections(uid, "youtube") if r["account_id"]]
    checks = [db.channel_checked(uid, c) for c in channels]
    if any(not c or now - c >= DAY for c in checks):
        _soon(uid)
    return jsonify(items=items_for(uid), pending=uid in _RUNNING, checked_at=min(checks) if checks and all(checks) else None)


@app.post("/api/channel-videos/check")
def channel_video_check():
    """Check now: for a video just posted outside Pit Crew, or just deleted, without waiting for the daily check."""
    uid, now = g.user["id"], time.time()
    if now - _ASKED.get(uid, 0) >= CHECK_NOW_EVERY:
        _ASKED[uid] = now
        _soon(uid)
    return jsonify(ok=True)


@app.post("/api/channel-videos/<video_id>/remove")
def channel_video_clear(video_id):
    """Clear a "Removed or deleted from YouTube" card."""
    if not re.fullmatch(r"[\w-]{6,20}", video_id):
        return jsonify(error="That video isn't here any more."), 404
    db.channel_video_clear_gone(g.user["id"], video_id)
    return jsonify(ok=True)
