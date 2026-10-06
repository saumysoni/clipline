"""
Keeping storage cheap: what Pit Crew deletes, and when (decided October 2026).

  - A vlog's video (the original, and the small copy for choosing scenes): KEEP_ORIGINAL_HOURS (72) after the
    vlog was last edited (any change to one of its Shorts restarts the clock). Everything made from it stays.
  - A draft Short (on neither YouTube nor Instagram, nor planned for either): KEEP_DRAFT_DAYS (30) after it was last
    edited. The Short is removed.
  - A posted Short's video file: KEEP_POSTED_DAYS (30) after it went out everywhere it was planned. Its record,
    thumbnail, link and numbers stay; it's then downloaded from YouTube Studio.

Each setting is in .env; 0 keeps forever. The creator is warned a day before a video or draft goes: on the card
and by email (printed in the terminal when email isn't set up). Nothing is deleted while it's being made, remade or
posted. A background check runs every 15 minutes (in the cloud this becomes a scheduled job).
"""
import json
import os
import re
import shutil
import threading
import time
import traceback
from datetime import datetime, timezone

from accounts import db, mail
from settings import JOBS_DIR

from web.posting import POSTING
from web.store import JOBS, LOCK, load_job, update
from web.vlogs import created_at, remove_video

WARN_BEFORE = 24 * 3600
CHECK_EVERY = 15 * 60
IG_PENDING = ("waiting", "posting", "check", "error")


def _setting(name, default):
    try:
        return max(0.0, float(os.getenv(name, default)))
    except ValueError:
        return float(default)


def keep_original():
    return _setting("KEEP_ORIGINAL_HOURS", 72) * 3600


def keep_draft():
    return _setting("KEEP_DRAFT_DAYS", 30) * 86400


def keep_posted():
    return _setting("KEEP_POSTED_DAYS", 30) * 86400


def _when(iso):
    return datetime.fromisoformat(iso).timestamp() if iso else None


def video_expires(job):
    """When this vlog's video will be deleted (seconds), or None (kept forever / already gone)."""
    if not keep_original() or job.get("video_deleted_at"):
        return None
    return (job.get("last_edit_at") or created_at(job)) + keep_original()


def is_draft(job, s):
    return not any(u["idx"] == s["idx"] for u in job.get("uploads") or []) and \
        not any(p["idx"] == s["idx"] for p in job.get("ig_posts") or [])


def draft_expires(job, s):
    """When this draft Short will be deleted (seconds), or None (not a draft / kept forever)."""
    if not keep_draft() or s.get("pending") or not is_draft(job, s):
        return None
    last = s.get("edited_at") or job.get("last_edit_at")
    if not last:
        f = JOBS_DIR / job["id"] / s.get("video", "")
        last = f.stat().st_mtime if s.get("video") and f.exists() else created_at(job)
    return last + keep_draft()


def posted_done_at(job, s):
    """When this Short finished going out everywhere it was planned (seconds), or None if something's still to go."""
    if any(p["idx"] == s["idx"] and p["status"] in IG_PENDING for p in job.get("ig_posts") or []):
        return None
    times = []
    for u in job.get("uploads") or []:
        if u["idx"] == s["idx"]:
            t = _when(u.get("when")) or _when(u.get("uploaded_at"))
            if t is None or t > time.time():  # unknown time, or not public yet
                return None
            times.append(t)
    for p in job.get("ig_posts") or []:
        if p["idx"] == s["idx"] and p["status"] == "done":
            times.append(_when(p.get("posted_at")) or time.time())
    return max(times) if times else None


def file_expires(job, s):
    if not keep_posted() or s.get("file_deleted_at"):
        return None
    done = posted_done_at(job, s)
    return done + keep_posted() if done else None


def _short_files(job_dir, s):
    """Every file belonging to a Short: its video, thumbnail, captions, thumbnail work folder, covered copies."""
    out = []
    for key in ("video", "thumb"):
        if s.get(key):
            out.append(job_dir / s[key])
    num = re.findall(r"_(\d+)\.", s.get("video") or "")
    if num:
        out.append(job_dir / f"captions_{num[0]}.ass")
    tnum = re.findall(r"_(\d+)\.", s.get("thumb") or "")
    if tnum:
        out.append(job_dir / f"thumbwork_{tnum[0]}")
    stem = os.path.splitext(s.get("video") or "")[0]
    if stem:
        out += list(job_dir.glob(f"cover_*{stem}_*"))
    return out


def _remove(paths):
    for p in paths:
        try:
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)
        except OSError as e:
            print(f"Couldn't delete {p.name}: {e}")


def _busy(job):
    return (job.get("status") != "ready" or job["id"] in POSTING
            or job.get("upload_status") in ("starting", "connecting", "uploading")
            or (job.get("vpost") or {}).get("state") == "uploading"
            or any(s.get("retrying") for s in job.get("shorts", [])))


def _email(owner, subject, text):
    user = db.user_by_id(owner) if owner else None
    if user:
        mail.notify(user["email"], subject, text)


def _date(t):
    return datetime.fromtimestamp(t).strftime("%a %b %-d, %-I:%M %p")


def sweep_job(job_id, now=None):
    """Apply the rules to one vlog. Returns what was done (for the log and tests)."""
    now = now or time.time()
    done = []
    with LOCK:
        job = load_job(job_id)
        if not job or _busy(job):
            return done
        job = json.loads(json.dumps(job, default=str))
    job_dir = JOBS_DIR / job_id
    title = (job.get("vlog") or {}).get("title") or job.get("name") or "your vlog"

    # 1. the vlog's video
    exp = video_expires(job)
    if exp and next(job_dir.glob("source.*"), None):
        if now >= exp:
            remove_video(job_id)
            done.append("video deleted")
        elif now >= exp - WARN_BEFORE and job.get("warned_video") != exp:
            _email(job.get("owner"), f"Pit Crew: the video of \"{title}\" will be deleted {_date(exp)}",
                   f"To keep storage free, Pit Crew deletes a vlog's video {keep_original() / 3600:.0f} hours after "
                   f"it was last edited. The video of \"{title}\" will be deleted on {_date(exp)}.\n\n"
                   "Its Shorts, thumbnails, transcript and posts all stay. After that, making new Shorts from it, or "
                   "changing a Short's hook or moment, needs the vlog uploaded again.\n\n"
                   "Still working on it? Any edit to one of its Shorts keeps the video for another "
                   f"{keep_original() / 3600:.0f} hours.\n")
            update(job_id, warned_video=exp)
            done.append("video warning")

    # 2. drafts, and 3. posted Shorts' video files
    gone, warn = [], []
    for s in job.get("shorts", []):
        exp = draft_expires(job, s)
        if exp and now >= exp:
            gone.append(s)
        elif exp and now >= exp - WARN_BEFORE and s.get("warned_at") != exp:
            warn.append((s, exp))
        fexp = file_expires(job, s)
        if fexp and now >= fexp and (job_dir / s.get("video", "")).is_file():
            _remove([job_dir / s["video"]] + list(job_dir.glob(f"cover_*{os.path.splitext(s['video'])[0]}_*")))
            with LOCK:
                live = JOBS.get(job_id) or load_job(job_id)
                live["shorts"] = [{**x, "file_deleted_at": now} if x["idx"] == s["idx"] else x for x in live["shorts"]]
                (job_dir / "job.json").write_text(json.dumps(live, default=str), encoding="utf-8")
            done.append(f"posted file {s['idx']} deleted")
    if gone:
        with LOCK:
            live = JOBS.get(job_id) or load_job(job_id)
            ids = {s["idx"] for s in gone if is_draft(live, s)}  # still drafts right now
            live["shorts"] = [x for x in live["shorts"] if x["idx"] not in ids]
            (job_dir / "job.json").write_text(json.dumps(live, default=str), encoding="utf-8")
        _remove([p for s in gone if s["idx"] in ids for p in _short_files(job_dir, s)])
        done += [f"draft {i} deleted" for i in sorted(ids)]
    if warn:
        names = "\n".join(f"  - {s.get('title') or 'Short ' + str(s['idx'])} (deleted {_date(exp)})" for s, exp in warn)
        n = len(warn)
        _email(job.get("owner"), f"Pit Crew: {n} draft{'s' if n > 1 else ''} from \"{title}\" will be deleted tomorrow",
               f"To keep storage free, Pit Crew deletes Shorts that weren't posted {keep_draft() / 86400:.0f} days "
               f"after they were last edited. From \"{title}\":\n\n{names}\n\n"
               "To keep one, post or schedule it, or edit it (any change keeps it for another "
               f"{keep_draft() / 86400:.0f} days). You can also download it first.\n")
        with LOCK:
            live = JOBS.get(job_id) or load_job(job_id)
            stamp = {s["idx"]: exp for s, exp in warn}
            live["shorts"] = [{**x, "warned_at": stamp[x["idx"]]} if x["idx"] in stamp else x for x in live["shorts"]]
            (job_dir / "job.json").write_text(json.dumps(live, default=str), encoding="utf-8")
        done.append(f"{n} draft warning(s)")
    return done


def sweep():
    for path in sorted(JOBS_DIR.glob("*/job.json")):
        if not re.fullmatch(r"[0-9a-f]{10}", path.parent.name):
            continue
        try:
            for what in sweep_job(path.parent.name):
                print(f"Storage clean-up, vlog {path.parent.name}: {what}")
        except Exception:  # noqa: BLE001  (one vlog's problem never stops the others)
            traceback.print_exc()


def _loop():
    time.sleep(60)  # let Pit Crew finish starting first
    while True:
        sweep()
        time.sleep(CHECK_EVERY)


if os.getenv("RETENTION_OFF") != "1":
    threading.Thread(target=_loop, daemon=True, name="storage-clean-up").start()
