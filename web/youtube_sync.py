"""
Keeping Pit Crew's upload records in step with YouTube: a Short the creator deleted in YouTube Studio (for example a
scheduled one they cancelled) is forgotten, so it becomes a draft again that can be scheduled again or deleted.

Checked when Shorts & Reels or Scheduled is opened, at most once a minute per creator (videos.list: 1 quota unit
per 50 Shorts). Only records that say which channel they went to, on a channel that's still connected, are touched:
"not found" is then certain. Network trouble or any YouTube error changes nothing.
"""
import json
import threading
import time
import traceback

import youtube as yt
from settings import JOBS_DIR

from web.posting import POSTING
from web.store import JOBS, LOCK, load_job
from web.vlogs import user_jobs

EVERY = 60  # seconds between checks per creator
_LAST = {}
_BUSY = threading.Lock()


def _forget(job_id, gone):
    with LOCK:
        job = load_job(job_id)
        if not job or job_id in POSTING:
            return 0
        before = len(job.get("uploads") or [])
        job["uploads"] = [u for u in job.get("uploads") or [] if (u["idx"], u.get("video_id")) not in gone]
        if len(job["uploads"]) == before:
            return 0
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
        by_channel = {}  # channel -> [(job id, idx, video id)]
        for job in user_jobs(user_id):
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
                if vid not in states:
                    gone.setdefault(job_id, set()).add((idx, vid))
            for job_id, pairs in gone.items():
                forgotten += _forget(job_id, pairs)
        if forgotten:
            print(f"{forgotten} Short(s) were deleted on YouTube: they're drafts again.")
        return forgotten
