"""
The On YouTube page: every uploaded Short, changing its time, updating it after an edit, unmarking it.
"""
import json
import re
import threading
import traceback
from datetime import datetime

from flask import abort, g, jsonify, request

import youtube as yt
from settings import JOBS_DIR

from web.posting import POSTING, do_upload, youtube_title
from web.server import app
from web.store import JOBS, LOCK, load_job, update, update_short


def posted_shorts(user_id):
    """Every upload record from this user's jobs, newest vlog first, with the job's id and vlog name."""
    with LOCK:
        ids = {p.parent.name for p in JOBS_DIR.glob("*/job.json")} | set(JOBS)
        jobs = [load_job(i) for i in ids if re.fullmatch(r"[0-9a-f]{10}", i)]
        jobs = [json.loads(json.dumps(j, default=str)) for j in jobs
                if j and j.get("uploads") and j.get("owner") == user_id]
    out = []
    for j in sorted(jobs, key=lambda j: (JOBS_DIR / j["id"] / "job.json").stat().st_mtime
                    if (JOBS_DIR / j["id"] / "job.json").exists() else 0, reverse=True):
        shorts = {s["idx"]: s for s in j.get("shorts", [])}
        vlog = (j.get("vlog") or {}).get("title") or j.get("name") or "Your vlog"
        for u in j["uploads"]:
            s = shorts.get(u["idx"], {})
            out.append({**u, "job": j["id"], "vlog": vlog, "thumb": u.get("thumb") or s.get("thumb", ""),
                        "changed": bool(s) and (s.get("video") != u.get("video", s.get("video")))})
    return out


@app.get("/api/posted")
def posted():
    uid = g.user["id"]
    items, live, note = posted_shorts(uid), False, None
    acct = yt.account(uid)
    me = (acct.get("channel") or {}).get("id")
    if items and acct["signed_in"]:
        try:
            states = yt.video_states(yt.get_service(uid), [u["video_id"] for u in items])
            for u in items:
                if u.get("channel") and me and u["channel"] != me:
                    u["state"] = {"privacy": "other_channel"}
                else:  # not found: deleted in Studio, or (older records) uploaded to another channel.
                    u["state"] = states.get(u["video_id"]) or {"privacy": "missing"}  # the creator decides
            live = True
        except Exception as e:
            traceback.print_exc()
            note = "Couldn't check YouTube right now, so this shows what Clipline remembers. " + yt.upload_error_message(e)
    return jsonify(items=items, live=live, note=note, signed_in=acct["signed_in"])


@app.post("/api/unmark/<job_id>/<int:idx>")
def unmark(job_id, idx):
    """The creator says this Short is no longer on YouTube: forget the upload so it can go up again."""
    with LOCK:
        job, rec, _ = find_upload(job_id, idx)
    if not job:
        return jsonify(error="Wait until posting has finished."), 400
    forget_upload(job_id, idx)
    return jsonify(ok=True)


def find_upload(job_id, idx):
    """(job copy, upload record, current Short) for a posted Short. Call with LOCK held."""
    job = load_job(job_id)
    if not job:
        abort(404)
    rec = next((u for u in job.get("uploads") or [] if u["idx"] == idx), None)
    short = next((s for s in job.get("shorts", []) if s["idx"] == idx and not s.get("pending")), None)
    if not rec or not short:
        abort(404)
    if job_id in POSTING:
        return None, None, None
    return job, dict(rec), dict(short)


def forget_upload(job_id, idx):
    with LOCK:
        job = JOBS[job_id]
        job["uploads"] = [u for u in job.get("uploads") or [] if u["idx"] != idx]
        (JOBS_DIR / job_id / "job.json").write_text(json.dumps(job, default=str), encoding="utf-8")


GONE = ("Clipline can't find this Short on the YouTube channel you connected. If you deleted it in YouTube "
        "Studio, use Unmark it on the My scheduled Shorts page, then upload it again. If it's on another "
        "channel, connect that channel first.")


@app.post("/api/reschedule/<job_id>/<int:idx>")
def reschedule(job_id, idx):
    """Give a scheduled Short a new time (the creator's local time + time zone from the browser)."""
    data = request.get_json(force=True)
    with LOCK:
        job, rec, _ = find_upload(job_id, idx)
    if not job:
        return jsonify(error="Wait until posting has finished."), 400
    try:
        when = yt.plan_times(1, "custom", data.get("tz"), data.get("start"))[0]
        service = yt.get_service(g.user["id"])
        if not yt.video_states(service, [rec["video_id"]]):
            return jsonify(error=GONE), 400
        yt.reschedule(service, rec["video_id"], when)
    except Exception as e:
        traceback.print_exc()
        return jsonify(error=yt.upload_error_message(e)), 400
    with LOCK:
        j = JOBS[job_id]
        j["uploads"] = [{**u, "when": when.isoformat()} if u["idx"] == idx else u for u in j["uploads"]]
        (JOBS_DIR / job_id / "job.json").write_text(json.dumps(j, default=str), encoding="utf-8")
    return jsonify(ok=True, when=when.isoformat())


@app.post("/api/repost/<job_id>/<int:idx>")
def repost(job_id, idx):
    """Bring an uploaded Short up to date after editing it in Clipline.
    Title only: change the title on YouTube. New video (hook, moment): upload the new version with the
    same time, then delete the old one. Never for a Short that's already public (it would lose its views)."""
    data = request.get_json(force=True)
    with LOCK:
        job, rec, short = find_upload(job_id, idx)
        if job and short.get("retrying"):
            return jsonify(error="Wait until this Short has finished being remade."), 400
    if not job:
        return jsonify(error="Wait until posting has finished."), 400
    title = (data.get("title") or short["title"]).strip()[:95]
    try:
        service = yt.get_service(g.user["id"])
        state = yt.video_states(service, [rec["video_id"]]).get(rec["video_id"])
        if not state:
            return jsonify(error=GONE), 400
        if short["video"] == rec.get("video", short["video"]):
            if title == rec["title"]:
                return jsonify(error="Nothing has changed since it was uploaded. Edit the title, hook or moment first."), 400
            yt.update_title(service, rec["video_id"], youtube_title(title))
            with LOCK:
                j = JOBS[job_id]
                j["uploads"] = [{**u, "title": title} if u["idx"] == idx else u for u in j["uploads"]]
                (JOBS_DIR / job_id / "job.json").write_text(json.dumps(j, default=str), encoding="utf-8")
            update_short(job_id, idx, title=title)
            return jsonify(ok=True, done="title")
    except Exception as e:
        traceback.print_exc()
        return jsonify(error=yt.upload_error_message(e)), 400
    if yt.is_live(state):
        return jsonify(error="This Short is already public. Replacing it would delete its views and comments, so "
                             "Clipline won't do that. Change it in YouTube Studio, or use Add a Short to post "
                             "the edited moment as a new Short."), 400
    when = None
    if rec.get("when"):
        when = datetime.fromisoformat(rec["when"])
        if when < datetime.now(when.tzinfo) + yt.MIN_LEAD:
            return jsonify(error="This Short goes public in less than 15 minutes, too soon to replace it. "
                                 "Change its time first."), 400
    with LOCK:
        if job_id in POSTING:
            return jsonify(error="Wait until posting has finished."), 400
        POSTING.add(job_id)
        earlier = list(JOBS[job_id].get("uploads") or [])
    update_short(job_id, idx, title=title)
    update(job_id, upload_status="starting", upload_msg="Starting")
    item = {**short, "title": title, "replace": rec}
    threading.Thread(target=do_upload, args=(g.user["id"], job_id, [item], "replace", [when], earlier),
                     daemon=True).start()
    return jsonify(ok=True, done="replace")
