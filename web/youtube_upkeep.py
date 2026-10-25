"""
YouTube's rules for data Pit Crew keeps (YouTube API Services Developer Policies III.E.4 and III.D.2), checked once a
day for every account:

  - Each connected channel's sign-in is refreshed and its name, @handle and picture read again at least every
    CHECK_DAYS (7; the rule is 30). Access removed in the Google account shows up here (Google answers invalid_grant)
    and the connection is dropped (youtube/connection.load_creds).
  - Every Short and vlog Pit Crew put on a connected channel is checked to still be there (web/youtube_sync.py: gone
    ones are forgotten).
  - A channel Pit Crew still has records about but that isn't connected any more (disconnected in Pit Crew, or access
    removed in the Google account) is forgotten GONE_DAYS (5) after it was first seen gone: its upload records (the
    Shorts become drafts again, as when they're deleted in YouTube Studio), the vlog's video id and link, and the
    numbers in memory. The rules allow 7 days after a disconnect and 30 after a removal in Google's settings.
    Connecting the channel again within those days keeps everything.
  - A vlog's details read from its YouTube link (description, tags, channel) are read again when LINK_DAYS (30) old,
    and deleted if YouTube doesn't show them any more. The title stays: the creator saw or typed it in the form, and
    it's the vlog's name in Pit Crew.
  - Numbers kept in memory are never older than 30 days (youtube/stored_data.py).

Deleting an account deletes all of it at once (web/delete_account.py). RETENTION_OFF=1 stops this timer too (tests).
"""
import json
import os
import threading
import time
import traceback

import youtube as yt
from accounts import db
from settings import JOBS_DIR

from web.posting import POSTING
from web.store import JOBS, LOCK, load_job
from web.vlogs import created_at, user_jobs
from web.youtube_sync import sync_deleted

DAY = 24 * 3600
CHECK_DAYS = 7
GONE_DAYS = 5
LINK_DAYS = 30
LINK_FIELDS = ("description", "tags", "channel", "channel_id", "channel_handle", "video_id", "complete")
BUSY_STATES = ("working", "queued")


def _save(job):
    JOBS[job["id"]] = job
    (JOBS_DIR / job["id"] / "job.json").write_text(json.dumps(job, default=str), encoding="utf-8")


def _busy(job):
    from web.vlog_upload import UPLOADING
    return job["id"] in POSTING or job["id"] in UPLOADING or job.get("status") in BUSY_STATES


def recheck_channels(user_id, now):
    """Refresh each connected channel whose details are older than CHECK_DAYS. Returns how many were checked."""
    n = 0
    for row in db.connections(user_id, "youtube"):
        if row["account_id"] and now - ((row["profile"] or {}).get("checked_at") or 0) >= CHECK_DAYS * DAY:
            print(f"YouTube upkeep, user {user_id}: channel {row['account_id']} {yt.recheck(row)}")
            n += 1
    return n


def channels_in_records(job):
    """The YouTube channels a job's records mention: its Shorts' uploads and, for a vlog upload, the vlog."""
    found = {u.get("channel") for u in job.get("uploads") or []}
    found.add((job.get("vpost") or {}).get("channel"))
    return found - {None, ""}


def forget_channel(user_id, channel):
    """Delete what Pit Crew knows from YouTube about one channel. Returns (records deleted, vlogs left for later
    because they're being made or posted right now)."""
    n = later = 0
    for snap in user_jobs(user_id):
        with LOCK:
            job = load_job(snap["id"])
            if not job or channel not in channels_in_records(job):
                continue
            if _busy(job):
                later += 1
                continue
            before = len(job.get("uploads") or [])
            job["uploads"] = [u for u in job.get("uploads") or [] if u.get("channel") != channel]
            n += before - len(job["uploads"])
            post = dict(job.get("vpost") or {})
            if post.get("channel") == channel:
                for k in ("video_id", "channel"):
                    post.pop(k, None)
                job["vpost"] = {**post, "forgotten_at": time.time()}
                vlog = dict(job.get("vlog") or {})
                for k in ("video_id", "youtube_url", "channel", "channel_id", "channel_handle"):
                    vlog.pop(k, None)
                job["vlog"] = vlog
                n += 1
            _save(job)
    yt.forget_old_numbers(gone_channels=[channel])
    return n, later


def forget_gone_channels(user_id, now, jobs=None):
    """Channels in records that aren't connected: note when they went, forget them GONE_DAYS later. Returns the
    channels forgotten."""
    connected = {r["account_id"] for r in db.connections(user_id, "youtube") if r["account_id"]}
    mentioned = set()
    for job in jobs if jobs is not None else user_jobs(user_id):
        mentioned |= channels_in_records(job)
    for ch in mentioned & connected:
        db.clear_gone(user_id, ch)
    out = []
    for ch in sorted(mentioned - connected):
        if now - db.gone_since(user_id, ch, now) >= GONE_DAYS * DAY:
            n, later = forget_channel(user_id, ch)
            if not later:  # else kept on the list: the rest goes on the next check
                db.clear_gone(user_id, ch)
            print(f"YouTube upkeep, user {user_id}: channel {ch} isn't connected any more: {n} record(s) forgotten"
                  + (f", {later} vlog(s) busy, next time" if later else ""))
            out.append(ch)
    return out


def refresh_vlog_links(user_id, now):
    """Read a vlog's YouTube details again once they're LINK_DAYS old; delete them if YouTube doesn't show them."""
    n = 0
    for snap in user_jobs(user_id):
        vlog = snap.get("vlog") or {}
        if snap.get("kind") == "vlog" or not vlog.get("youtube_url") or not any(k in vlog for k in LINK_FIELDS):
            continue
        age = now - (vlog.get("fetched_at") or created_at(snap))
        if age < LINK_DAYS * DAY:
            continue
        try:
            info = yt.fetch_video_info(vlog["youtube_url"], yt.access_token(user_id))
            fresh = {**{k: v for k, v in info.items() if k in LINK_FIELDS}, "fetched_at": now}
        except RuntimeError as e:
            # YouTube doesn't show it any more (deleted, private): delete. Offline or a refused lookup (e.g. quota):
            # try again tomorrow, for up to a week.
            if "couldn't find" not in str(e).lower() and age < (LINK_DAYS + 7) * DAY:
                continue
            fresh = None
        with LOCK:
            job = load_job(snap["id"])
            if not job or _busy(job):
                continue
            kept = {k: v for k, v in (job.get("vlog") or {}).items() if k not in LINK_FIELDS and k != "fetched_at"}
            job["vlog"] = {**kept, **fresh} if fresh else {**kept, "fetched_at": now}
            _save(job)
        n += 1
    return n


def upkeep(user_id, now=None):
    now = now or time.time()
    recheck_channels(user_id, now)
    sync_deleted(user_id, force=True)
    forget_gone_channels(user_id, now)
    refresh_vlog_links(user_id, now)


def sweep(now=None):
    for uid in db.user_ids():
        try:
            upkeep(uid, now)
        except Exception:  # noqa: BLE001  (one account's problem never stops the others)
            traceback.print_exc()
    try:
        yt.forget_old_numbers(now=now)
    except Exception:  # noqa: BLE001
        traceback.print_exc()


def _loop():
    time.sleep(300)  # after Pit Crew has started (and the storage clean-up's first run)
    while True:
        sweep()
        time.sleep(DAY)


if os.getenv("RETENTION_OFF") != "1":
    threading.Thread(target=_loop, daemon=True, name="youtube-upkeep").start()
