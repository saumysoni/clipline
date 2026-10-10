"""
Emails when something finishes while the creator is away: Shorts ready, a vlog ready to upload, a vlog that stopped
(with Try again), and posting that failed (YouTube Shorts, a whole vlog, an Instagram Reel).

No email while the creator is watching that vlog's page (it asked for progress in the last WATCH_SECS), and only to
confirmed emails (web/verify_email.py), so someone who signs up with another person's address can't send them mail.
Sent in a background thread: SMTP can take seconds and must never hold up a job or the Instagram scheduler.
"""
import os
import threading
import time

from accounts import db, mail

from web.store import JOBS, LOCK, load_job


WATCH_SECS = 20
WATCHING = {}  # job id -> when its page last asked for progress (web/job_status.py)


def watched(job_id):
    return time.time() - WATCHING.get(job_id, 0) < WATCH_SECS


def app_link(fragment):
    """A link into Pit Crew for an email. Background threads have no request, so this is APP_URL (set it in the
    cloud), else the local address."""
    return f"{(os.getenv('APP_URL') or 'http://localhost:8000').rstrip('/')}/#{fragment}"


def _job(job_id):
    with LOCK:
        job = JOBS.get(job_id) or load_job(job_id) or {}
        return dict(job)


def _title(job):
    return (job.get("vlog") or {}).get("title") or (job.get("vdraft") or {}).get("title") or job.get("name") or "your vlog"


def _send(user_id, subject, text, job_id=None):
    if job_id and watched(job_id):
        return
    user = db.user_by_id(user_id) if user_id else None
    if not user or not user["email_verified"]:
        return
    threading.Thread(target=mail.notify, args=(user["email"], subject, text), daemon=True).start()


def _kept():
    from web.retention import keep_original  # (retention imports web/posting, which imports this file)
    hours = keep_original() / 3600
    return f" Pit Crew keeps the video for {hours:.0f} hours." if hours else ""


def shorts_ready(job_id):
    job = _job(job_id)
    n, title = len(job.get("shorts") or []), _title(job)
    _send(job.get("owner"), f"Your {n} Short{'s' if n != 1 else ''} from \"{title}\" {'are' if n != 1 else 'is'} ready",
          f"Pit Crew finished making {n} Short{'s' if n != 1 else ''} from \"{title}\".\n\n"
          f"Watch them, pick the ones you like, and post or schedule them:\n{app_link(job_id)}\n", job_id)


def vlog_ready(job_id):
    job = _job(job_id)
    title = _title(job)
    _send(job.get("owner"), f"\"{title}\" is ready to upload",
          f"Pit Crew wrote title ideas, a description with chapters, tags and a thumbnail for \"{title}\".\n\n"
          f"Check them and upload it to YouTube:\n{app_link('vlog/' + job_id)}\n", job_id)


def stopped(job_id, reason):
    from settings import JOBS_DIR

    job = _job(job_id)
    title = _title(job)
    if next((JOBS_DIR / job_id).glob("source.*"), None):  # Try again works on the video Pit Crew has
        what = f"Open it and press Try again (no need to upload it again):\n{app_link(job_id)}\n\n{_kept().strip()}\n"
    else:  # e.g. a Google Drive link that couldn't be downloaded
        what = f"Pit Crew doesn't have the video, so upload it again:\n{app_link('')}\n"
    _send(job.get("owner"), f"Pit Crew stopped working on \"{title}\"", f"{reason}\n\n{what}{_help(job_id)}", job_id)


def _help(job_id):
    support = os.getenv("SUPPORT_EMAIL", "").strip()
    return f"\nNeed help? Write to {support} and mention reference {job_id}.\n" if support else ""


def post_failed(job_id, where, reason, fragment=None):
    """where: "YouTube" / "Instagram". fragment: the page to open (default: the vlog's Shorts)."""
    job = _job(job_id)
    title = _title(job)
    _send(job.get("owner"), f"Posting to {where} didn't work (\"{title}\")",
          f"Pit Crew couldn't post to {where} from \"{title}\":\n\n{reason}\n\n"
          f"Open it to try again:\n{app_link(fragment or job_id)}\n{_help(job_id)}", job_id)
