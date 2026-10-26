"""
YouTube's daily upload limit, shared by everyone (decided Oct 2026, with Saumya).

YouTube gives one Google Cloud project YOUTUBE_DAILY_UPLOADS (100) video uploads a day, reset at midnight Pacific time,
and Pit Crew is one project. Using several projects to get more is against YouTube's API terms; Google's audit raises
the number instead (then change the setting).

  - Open: until YOUTUBE_OPEN_SHARE (60) % of the day's uploads are used, anyone uploads as much as they like.
  - Fair shares: after that, what's left (minus YOUTUBE_RESERVE, 5, kept for Replace) is split between the creators who
    posted today plus room for one more (someone posting for the first time later in the day still gets a share).
  - Never a failure: a Short (or a vlog) over its share, or when the day is used up, waits in Pit Crew (job["yt_waiting"],
    vpost state "waiting") and goes up by itself after the reset, oldest first. Its public time stays; one whose time
    has passed by then goes public as soon as it's up.

Replacing an edited Short may use the reserve. Every upload (Shorts, vlogs, Replace) is counted here, per Pacific day,
in accounts/db.py (youtube_uploads). If YouTube itself says the quota is used up before our count does, the rest of
the day counts as used up.
"""
import json
import math
import os
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import g, jsonify

from accounts import db
from settings import JOBS_DIR

from web.server import app
from web.store import JOBS, LOCK, load_job

PACIFIC = ZoneInfo("America/Los_Angeles")
_LOCK = threading.Lock()
_WAKE = threading.Event()
CHECK_EVERY = 300  # seconds between looks at the waiting uploads


def _setting(name, default):
    try:
        return max(0, int(os.getenv(name, default)))
    except ValueError:
        return default


def limit():
    return _setting("YOUTUBE_DAILY_UPLOADS", 100)


def reserve():
    return min(_setting("YOUTUBE_RESERVE", 5), limit())


def open_until():
    return math.floor(limit() * min(100, _setting("YOUTUBE_OPEN_SHARE", 60)) / 100)


def today(now=None):
    return datetime.fromtimestamp(now or time.time(), PACIFIC).strftime("%Y-%m-%d")


def resets_at(now=None):
    """The next midnight Pacific (aware UTC datetime)."""
    d = datetime.fromtimestamp(now or time.time(), PACIFIC)
    nxt = datetime(d.year, d.month, d.day, tzinfo=PACIFIC) + timedelta(days=1)
    return nxt.astimezone(timezone.utc)


def _share(counts, user_id):
    """This creator's fair share after the open part (number of uploads), given today's counts."""
    pool = max(0, limit() - reserve() - open_until())
    posting = {u for u, (n, _) in counts.items() if n > 0 and u > 0} | {user_id}
    return max(1, pool // (len(posting) + 1))


def status(user_id, now=None):
    """What the page shows: today's numbers and how many more this creator can upload today (None = no cap now)."""
    day = today(now)
    counts = db.youtube_uploads(day)
    used = sum(n for u, (n, _) in counts.items() if u > 0)
    if db.youtube_exhausted(day):
        used = max(used, limit())
    usable = limit() - reserve()
    mine, mine_fair = counts.get(user_id, (0, 0))
    if used < open_until():
        left = None  # open part: no cap per creator (the day's total still applies)
        day_left = usable - used
    else:
        day_left = max(0, usable - used)
        left = min(day_left, max(0, _share(counts, user_id) - mine_fair))
    return {"limit": limit(), "used": used, "open_until": open_until(), "left_today": left,
            "day_left": max(0, day_left), "mine_today": mine, "resets_at": resets_at(now).isoformat()}


def take(user_id, kind="short", now=None):
    """Count one upload for this creator now, if it fits: "open" or "fair" (which part of the day it was counted in, for
    give_back); None means it should wait for the reset. kind: "short", "vlog" or "replace" (Replace may use the
    reserve)."""
    with _LOCK:
        day = today(now)
        if db.youtube_exhausted(day):
            return None
        counts = db.youtube_uploads(day)
        used = sum(n for u, (n, _) in counts.items() if u > 0)
        if kind == "replace":
            if used >= limit():
                return None
            db.add_youtube_upload(day, user_id, fair=False)
            return "open"
        if used >= limit() - reserve():
            return None
        if used < open_until():
            db.add_youtube_upload(day, user_id, fair=False)
            return "open"
        if counts.get(user_id, (0, 0))[1] >= _share(counts, user_id):
            return None
        db.add_youtube_upload(day, user_id, fair=True)
        return "fair"


def give_back(user_id, counted, now=None):
    """An upload that was counted (take() said "open" or "fair") but never reached YouTube."""
    if counted:
        with _LOCK:
            db.remove_youtube_upload(today(now), user_id, counted == "fair")


def youtube_says_used_up(now=None):
    """YouTube answered quotaExceeded: the rest of today counts as used up, whatever our count says."""
    db.set_youtube_exhausted(today(now))


def is_quota_error(e):
    """YouTube's own "used up for today" answers: wait for the reset instead of failing."""
    from googleapiclient.errors import HttpError
    if not isinstance(e, HttpError):
        return False
    try:
        reason = json.loads(e.content.decode("utf-8"))["error"]["errors"][0].get("reason", "")
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        return False
    return reason in ("quotaExceeded", "uploadLimitExceeded", "dailyLimitExceeded")


# ---------------------------------------------------------------- waiting uploads -----------------------------------

def defer(job_id, user_id, channel, rows):
    """Keep these Shorts in Pit Crew until the reset. rows: [(item, when)] with item a Short (its idx and title)."""
    now = time.time()
    with LOCK:
        job = load_job(job_id)
        waiting = [w for w in job.get("yt_waiting") or [] if w["idx"] not in {it["idx"] for it, _ in rows}]
        waiting += [{"idx": it["idx"], "title": it["title"], "when": when.isoformat() if when else None,
                     "channel": channel, "owner": user_id, "queued_at": now} for it, when in rows]
        job["yt_waiting"] = waiting
        JOBS[job_id] = job
        (JOBS_DIR / job_id / "job.json").write_text(json.dumps(job, default=str), encoding="utf-8")
    _WAKE.set()


def waiting_message(n):
    at = resets_at().astimezone(PACIFIC)
    return (f"{n} Short{'s' if n != 1 else ''} will go up to YouTube after midnight Pacific time "
            f"({at:%b} {at.day}): today's YouTube uploads for Pit Crew are used up. You don't need to do anything; "
            "the times you chose stay.")


def _jobs_waiting():
    out = []
    for path in JOBS_DIR.glob("*/job.json"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if '"yt_waiting"' not in text and '"waiting"' not in text:
            continue
        with LOCK:
            job = load_job(path.parent.name)
            if not job:
                continue
            job = json.loads(json.dumps(job, default=str))
        if job.get("yt_waiting") or (job.get("vpost") or {}).get("state") == "waiting":
            out.append(job)
    return out


def send_waiting():
    """Try the waiting uploads, oldest first (each still goes through take(), so shares apply). Returns how many
    jobs were started."""
    from web.posting import POSTING, do_upload
    from web.vlog_upload import UPLOADING, send_waiting_vlog
    started = 0
    jobs = sorted(_jobs_waiting(), key=lambda j: min([w["queued_at"] for w in j.get("yt_waiting") or []] +
                                                     [(j.get("vpost") or {}).get("queued_at") or 9e18]))
    for job in jobs:
        jid = job["id"]
        if (job.get("vpost") or {}).get("state") == "waiting" and jid not in UPLOADING:
            send_waiting_vlog(jid)
            started += 1
        waiting = job.get("yt_waiting") or []
        if not waiting or job.get("status") != "ready":
            continue
        with LOCK:
            if jid in POSTING:
                continue
            POSTING.add(jid)
            live = load_job(jid)
            by_idx = {s["idx"]: s for s in live.get("shorts", []) if not s.get("pending")}
            posted = {u["idx"] for u in live.get("uploads") or []}
            todo = [w for w in live.get("yt_waiting") or [] if w["idx"] in by_idx and w["idx"] not in posted]
            live["yt_waiting"] = []
            earlier = list(live.get("uploads") or [])
            (JOBS_DIR / jid / "job.json").write_text(json.dumps(live, default=str), encoding="utf-8")
        if not todo:
            with LOCK:
                POSTING.discard(jid)
            continue
        soon = datetime.now(timezone.utc) + timedelta(minutes=15)
        times = []
        for w in todo:
            t = datetime.fromisoformat(w["when"]) if w.get("when") else None
            times.append(t if t and t > soon else None)  # its time has passed: public as soon as it's up
        items = [{**by_idx[w["idx"]], "title": w["title"]} for w in todo]
        from web.store import update
        update(jid, upload_status="starting", upload_msg="Sending the Shorts that waited for YouTube's daily limit",
               upload_queue=[w["idx"] for w in todo])
        try:
            do_upload(todo[0]["owner"], jid, items, "custom", times, earlier, todo[0]["channel"])  # (clears POSTING)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        started += 1
    return started


def _loop():
    time.sleep(60)
    while True:
        try:
            if status(0)["day_left"] > 0:
                send_waiting()
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        until_reset = (resets_at() - datetime.now(timezone.utc)).total_seconds() + 30
        _WAKE.wait(min(CHECK_EVERY, max(5, until_reset)))
        _WAKE.clear()


@app.get("/api/youtube/today")
def youtube_today():
    from web.vlogs import user_jobs
    s = status(g.user["id"])
    mine = sum(len(j.get("yt_waiting") or []) for j in user_jobs(g.user["id"]))
    return jsonify(**s, waiting=mine)


if os.getenv("RETENTION_OFF") != "1":
    threading.Thread(target=_loop, daemon=True, name="youtube-waiting").start()
