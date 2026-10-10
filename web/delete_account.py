"""
Delete account (Settings): everything Pit Crew keeps for this creator goes. Every vlog and Short (videos, thumbnails,
transcripts, plans; Reels still waiting are never posted), the saved transcripts of their videos, the YouTube
connections (revoked at Google, as Disconnect does) and Instagram connections, Reel numbers, and the account itself.
What's already on YouTube or Instagram stays there. Refused while something is being made or posted, so no thread is
left writing into a deleted folder.
"""
import hashlib
import shutil

from flask import g, jsonify, request, session

import youtube as yt
from accounts import db
from pipeline.transcript_cache import TRANSCRIPTS_DIR
from settings import JOBS_DIR

from web.posting import POSTING
from web.preview import PREVIEWS, PREVIEW_PCT
from web.server import app
from web.stop_and_retry import STOPPING
from web.store import JOBS, LOCK
from web.video_upload import UPLOADS_DIR, _meta
from web.vlogs import user_jobs


def _busy(job):
    return (job.get("status") == "working" or job["id"] in POSTING
            or job.get("upload_status") in ("starting", "connecting", "uploading")
            or (job.get("vpost") or {}).get("state") == "uploading"
            or any(s.get("retrying") for s in job.get("shorts", []))
            or any(p.get("status") == "posting" for p in job.get("ig_posts") or []))


def _digest(path):
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


@app.post("/api/account/delete")
def delete_account():
    user = g.user
    typed = str(request.get_json(force=True).get("email", "")).strip().lower()
    if typed != user["email"]:
        return jsonify(error=f"Type your email exactly as it is ({user['email']}) to delete your account.",
                       field="email"), 400
    jobs = user_jobs(user["id"])
    with LOCK:  # a vlog being stopped is hidden from user_jobs(), but its thread is still finishing
        stopping = any((JOBS.get(i) or {}).get("owner") == user["id"] for i in STOPPING)
    if stopping:
        return jsonify(error="A vlog is still stopping. Wait a moment, then delete your account."), 400
    busy = next((j for j in jobs if _busy(j)), None)
    if busy:
        title = (busy.get("vlog") or {}).get("title") or busy.get("name") or "a vlog"
        return jsonify(error=f"Pit Crew is still working on \"{title}\". Wait until it's finished (or press Stop), "
                             "then delete your account."), 400

    # Saved transcripts (jobs/_transcripts, kept by the video's fingerprint, not by person): the ones of these videos.
    mine = {d for j in jobs if (d := _digest(JOBS_DIR / j["id"] / "transcript.json"))}
    with LOCK:
        for j in jobs:
            JOBS.pop(j["id"], None)
            PREVIEWS.pop(j["id"], None)
            PREVIEW_PCT.pop(j["id"], None)
            (JOBS_DIR / j["id"] / "job.json").unlink(missing_ok=True)  # first, so nothing loads it again
    for j in jobs:
        shutil.rmtree(JOBS_DIR / j["id"], ignore_errors=True)
    for f in TRANSCRIPTS_DIR.glob("*.json") if mine else ():
        if _digest(f) in mine:
            f.unlink(missing_ok=True)

    for d in UPLOADS_DIR.glob("*"):  # videos still being sent
        if (_meta(d.name) or {}).get("owner") == user["id"]:
            shutil.rmtree(d, ignore_errors=True)

    for _ in range(50):  # every YouTube channel, each revoked at Google (rows without a channel id too)
        if not db.connections(user["id"], "youtube"):
            break
        yt.sign_out(user["id"], None)
    db.delete_user(user["id"])  # Instagram connections, Reel numbers and links go with it
    session.clear()
    print(f"Deleted account {user['id']} and its {len(jobs)} vlog(s) at the creator's request.")
    return jsonify(ok=True)
