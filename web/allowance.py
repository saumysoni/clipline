"""
How much each creator can make: the longest vlog Pit Crew takes (MAX_VLOG_MINUTES, default 180) and how many minutes
of vlog one account can have made per calendar month, UTC (MONTHLY_VLOG_MINUTES, default 0 = no limit; set it in the
cloud: every minute is transcription, AI calls and editing on our bill).

Checked three times: before a video is sent (/api/upload/new: is this month's allowance used up?), when a start
request comes in (its length, read from the uploaded file), and in the job itself once the video is read (charge():
also covers Google Drive links). A vlog is charged once (job["charged"]), so Try again, a restart and making Shorts
from an uploaded vlog later don't count it again.
"""
import os
import threading
from datetime import datetime, timezone

from flask import g, jsonify

import pipeline
from accounts import db

from web.server import app
from web.store import LOCK, load_job, update


def _minutes(name, default):
    try:
        return max(0.0, float(os.getenv(name, default)))
    except ValueError:
        return float(default)


def longest():
    return _minutes("MAX_VLOG_MINUTES", 180)


def monthly():
    return _minutes("MONTHLY_VLOG_MINUTES", 0)


def _month(now=None):
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m")


def _next_month():
    now = datetime.now(timezone.utc)
    first = datetime(now.year + (now.month == 12), now.month % 12 + 1, 1)
    return f"{first:%B} {first.day}"


def _length(seconds):
    m = round(seconds / 60)
    if m < 1:
        return "less than a minute"
    return f"{m // 60} h {m % 60} min" if m >= 60 else f"{m} minute{'' if m == 1 else 's'}"


def problem(user_id, seconds=0.0):
    """Why this creator can't make a vlog of this length now (a plain sentence), or None. seconds=0: only "is this
    month's allowance used up"."""
    if longest() and seconds > longest() * 60:
        return (f"This vlog is {_length(seconds)} long. Pit Crew takes vlogs up to {_length(longest() * 60)}: "
                "trim it, or split it into parts and upload each one.")
    if monthly():
        left = monthly() * 60 - db.used_seconds(user_id, _month())
        if left <= 0:
            return (f"You've made this month's {_length(monthly() * 60)} of vlogs. Your allowance starts again on "
                    f"{_next_month()}.")
        if seconds > left:
            return (f"This vlog is {_length(seconds)} long, and you have {_length(left)} of vlogs left this month. "
                    f"Trim it, or upload it after your allowance starts again on {_next_month()}.")
    return None


CHARGING = threading.Lock()  # two vlogs of one creator starting together can't both take the last minutes


def charge(job_id, seconds):
    """Count a vlog against its creator's month, once. Raises RuntimeError (shown as it is) if it doesn't fit."""
    with LOCK:
        job = load_job(job_id) or {}
        owner, charged = job.get("owner"), job.get("charged")
    if charged or not owner:
        return
    with CHARGING:
        why = problem(owner, seconds)
        if why:
            raise RuntimeError(why)
        db.add_usage(owner, _month(), seconds)
        update(job_id, charged=seconds)


def upload_problem(upload_id, user_id):
    """Before a sent video becomes a vlog: is it a video Pit Crew can read, and does its length fit? Returns
    (message, drop the upload) or None (also None if it isn't finished: take_upload() says so)."""
    from web.video_upload import discard_upload, finished_upload  # (video_upload imports this file)

    path = finished_upload(upload_id, user_id)
    if not path:
        return None
    try:
        seconds = pipeline.probe(path)["duration"]
    except Exception as e:  # noqa: BLE001
        print("A sent file couldn't be read as a video:", repr(e)[:300])
        discard_upload(upload_id)
        return "That file isn't a video Pit Crew can read. Choose your vlog's video file.", True
    why = problem(user_id, seconds)
    return (why, False) if why else None


@app.get("/api/allowance")
def allowance():
    used = db.used_seconds(g.user["id"], _month()) / 60
    return jsonify(longest=longest(), monthly=monthly(), used=round(used, 1), resets=_next_month())
