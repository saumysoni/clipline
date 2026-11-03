"""
Keeping Pit Crew's upload records in step with YouTube, once a day per creator (web/youtube_upkeep.py, the creator's choice:
pages never ask). A Short that's gone from YouTube no longer counts as posted: it's a grey "Removed or deleted" card on Shorts
& Reels (job["yt_removed"], web/removed.py). One deleted while still only scheduled never went out, so it's a draft again. A vlog
Pit Crew uploaded that's gone gets vpost state "removed", the same card on the Videos page.

videos.list: 1 quota unit per 50 videos. Only records that say which channel they went to, on a channel that's still connected,
are touched: "not found" is then certain. Network trouble or any YouTube error changes nothing.
"""
import json
import threading
import time
import traceback
from datetime import datetime

import youtube as yt
from settings import JOBS_DIR

from web.posting import POSTING
from web.store import JOBS, LOCK, load_job
from web.vlogs import user_jobs

EVERY = 24 * 3600  # seconds between checks per creator
FRESH = 120  # seconds after uploading before a vlog is checked (YouTube is still taking it in)
_LAST = {}
_BUSY = threading.Lock()


def _vlog_removed(job_id, vid):
    """A vlog upload YouTube no longer has: mark it removed (kept: video_id, for Studio) and drop its dead link."""
    from web.vlog_upload import UPLOADING
    with LOCK:
        job = load_job(job_id)
        post = dict((job or {}).get("vpost") or {})
        if not job or job_id in UPLOADING or post.get("state") != "done" or post.get("video_id") != vid:
            return 0
        vlog = dict(job.get("vlog") or {})
        if vlog.get("video_id") == vid:
            vlog.pop("video_id", None)
            vlog.pop("youtube_url", None)
        job.update(vpost={**post, "state": "removed", "removed_at": time.time()}, vlog=vlog)
        JOBS[job_id] = job
        (JOBS_DIR / job_id / "job.json").write_text(json.dumps(job, default=str), encoding="utf-8")
        return 1


def _went_out(u, now):
    """False for one that was still only scheduled."""
    try:
        return not u.get("when") or datetime.fromisoformat(u["when"]).timestamp() <= now
    except (TypeError, ValueError):
        return True


def _forget(job_id, gone):
    with LOCK:
        job = load_job(job_id)
        if not job or job_id in POSTING:
            return 0
        now, before = time.time(), len(job.get("uploads") or [])
        out = [u for u in job.get("uploads") or [] if (u["idx"], u.get("video_id")) in gone]
        job["uploads"] = [u for u in job.get("uploads") or [] if (u["idx"], u.get("video_id")) not in gone]
        if len(job["uploads"]) == before:
            return 0
        lost = {u["idx"]: u for u in out if _went_out(u, now)}
        job["yt_removed"] = [r for r in job.get("yt_removed") or [] if r["idx"] not in lost] + \
            [{"idx": i, "channel": u.get("channel"), "removed_at": now} for i, u in lost.items()]
        JOBS[job_id] = job
        (JOBS_DIR / job_id / "job.json").write_text(json.dumps(job, default=str), encoding="utf-8")
        return before - len(job["uploads"])


def sync_deleted(user_id, force=False):
    """Forget uploads that no longer exist on their channel. Returns how many were forgotten."""
    now = time.time()
    if not force and now - _LAST.get(user_id, 0) < EVERY:
        return 0
    with _BUSY:
        _LAST[user_id] = now
        try:
            acct = yt.account(user_id)
        except Exception:  # noqa: BLE001
            return 0
        connected = {c["id"] for c in acct.get("channels") or []}
        by_channel = {}  # channel -> [(job id, idx, video id)]; idx None = the vlog itself (web/vlog_upload.py)
        for job in user_jobs(user_id):
            post = job.get("vpost") or {}
            if job.get("kind") == "vlog" and post.get("state") == "done" and post.get("video_id") and \
                    post.get("channel") in connected and now - (post.get("sent_at") or 0) > FRESH:
                by_channel.setdefault(post["channel"], []).append((job["id"], None, post["video_id"]))
            if job["id"] in POSTING:
                continue
            for u in job.get("uploads") or []:
                if u.get("video_id") and u.get("channel") in connected:
                    by_channel.setdefault(u["channel"], []).append((job["id"], u["idx"], u["video_id"]))
        forgotten = 0
        for channel, recs in by_channel.items():
            try:
                states = yt.video_states(yt.get_service(user_id, channel), [r[2] for r in recs])
            except Exception:  # noqa: BLE001  (can't check now: change nothing)
                traceback.print_exc()
                continue
            gone = {}
            for job_id, idx, vid in recs:
                if vid in states:
                    continue
                if idx is None:
                    if _vlog_removed(job_id, vid):
                        print(f"Vlog {job_id}: YouTube no longer has {vid} (deleted or removed by YouTube).")
                else:
                    gone.setdefault(job_id, set()).add((idx, vid))
            for job_id, pairs in gone.items():
                forgotten += _forget(job_id, pairs)
        if forgotten:
            print(f"{forgotten} Short(s) are gone from YouTube.")
        return forgotten
