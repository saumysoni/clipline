"""
Shorts & Reels page: every Short from every vlog of this creator, each with where it stands on YouTube and on
Instagram, and scheduling several at once (from different vlogs too) on one plan of times.

A clip's overall status: "draft" (not on either platform), "scheduled" (planned, not out yet), "posted" (out on at
least one), "failed" (its last upload or Reel didn't work).
"""
import json
import threading
from datetime import datetime, timezone

from flask import g, jsonify, request

import instagram as ig
import youtube as yt

from web.instagram_posting import DUE, _WAKE, _mutate
from web.posting import POSTING, do_upload
from web.retention import _remove, _short_files, draft_expires, is_draft
from web.server import app
from settings import JOBS_DIR
from web.store import JOBS, LOCK, load_job, update, update_short
from web.vlogs import created_at, user_jobs
from web.youtube_sync import sync_deleted

UPLOADING = ("starting", "connecting", "uploading")
IG_BUSY = ("waiting", "posting", "done", "check")


def _yt_state(job, s, now):
    up = next((u for u in job.get("uploads") or [] if u["idx"] == s["idx"]), None)
    if up:
        when = datetime.fromisoformat(up["when"]) if up.get("when") else None
        return {"state": "scheduled" if when and when > now else "posted", "when": up.get("when") or up.get("uploaded_at"),
                "video_id": up.get("video_id"), "channel": up.get("channel"), "channel_title": up.get("channel_title", "")}
    if s["idx"] in (job.get("upload_queue") or []):
        if job.get("upload_status") in UPLOADING:
            return {"state": "uploading", "msg": job.get("upload_msg", "")}
        if job.get("upload_status") == "error":
            return {"state": "failed", "error": job.get("upload_msg", "")}
    return None


def _ig_state(job, s):
    p = next((p for p in job.get("ig_posts") or [] if p["idx"] == s["idx"]), None)
    if not p:
        return None
    state = {"waiting": "scheduled", "posting": "posting", "done": "posted"}.get(p["status"], "failed")
    return {"state": state, "when": p.get("posted_at") if p["status"] == "done" else p.get("when"),
            "permalink": p.get("permalink", ""), "username": p.get("username", ""),
            "error": p.get("error", ""), "status": p["status"]}


def clip_list(user_id):
    now = datetime.now(timezone.utc)
    out = []
    for job in user_jobs(user_id):
        if job.get("status") != "ready":
            continue
        vlog = (job.get("vlog") or {}).get("title") or job.get("name") or "Your vlog"
        for s in job.get("shorts", []):
            if s.get("pending"):
                continue
            y, i = _yt_state(job, s, now), _ig_state(job, s)
            states = [x["state"] for x in (y, i) if x]
            status = ("failed" if "failed" in states else "posted" if "posted" in states
                      else "scheduled" if states else "draft")
            # when it went out (newest platform), for "Recently posted first"; scheduled/drafts have none
            posted_at = max([x["when"] for x in (y, i) if x and x["state"] == "posted" and x.get("when")],
                            key=datetime.fromisoformat, default=None)  # times may carry different time zones
            out.append({"job": job["id"], "vlog": vlog, "posted_at": posted_at, "vlog_created": created_at(job), "idx": s["idx"],
                        "title": s.get("title", ""), "thumb": s.get("thumb", ""), "video": s.get("video", ""),
                        "length": round((s.get("end") or 0) - (s.get("start") or 0)), "status": status,
                        "youtube": y, "instagram": i, "remaking": bool(s.get("retrying")),
                        "expires": draft_expires(job, s), "file_deleted": bool(s.get("file_deleted_at")),
                        "video_deleted": bool(job.get("video_deleted_at"))})
    out.sort(key=lambda c: (-c["vlog_created"], c["idx"]))
    return out


@app.get("/api/clips")
def clips():
    uid = g.user["id"]
    removed = sync_deleted(uid)  # Shorts deleted in YouTube Studio become drafts again
    return jsonify(items=clip_list(uid), removed_on_youtube=removed)


@app.post("/api/clips/schedule")
def clips_schedule():
    """Post or schedule several clips, from any of this creator's vlogs, on YouTube and/or Instagram, with one plan
    of times across all of them (in the order given). Each platform gets the same times."""
    data = request.get_json(force=True)
    uid = g.user["id"]
    want_yt, want_ig = bool(data.get("youtube")), bool(data.get("instagram"))
    if not want_yt and not want_ig:
        return jsonify(error="Pick YouTube, Instagram or both."), 400
    rows = []
    for r in data.get("items") or []:
        try:
            rows.append((str(r["job"]), int(r["idx"])))
        except (KeyError, TypeError, ValueError):
            return jsonify(error="Those clips couldn't be read. Refresh the page and try again."), 400
    if not rows:
        return jsonify(error="Tick at least one clip."), 400

    # Check every clip first, so nothing goes out when one of them can't.
    jobs = {}
    with LOCK:
        for jid, idx in rows:
            job = jobs.get(jid) or load_job(jid)
            if not job or job.get("owner") != uid or job.get("status") != "ready":
                return jsonify(error="One of those clips isn't available any more. Refresh the page."), 400
            if job["id"] in POSTING or job.get("upload_status") in UPLOADING:
                return jsonify(error="Some of these Shorts are already being posted. Wait until that's finished."), 400
            s = next((x for x in job["shorts"] if x["idx"] == idx and not x.get("pending")), None)
            if not s:
                return jsonify(error="One of those clips isn't available any more. Refresh the page."), 400
            if s.get("retrying"):
                return jsonify(error=f"\"{s['title']}\" is being remade. Wait until it's ready."), 400
            jobs[jid] = json.loads(json.dumps(job, default=str))

    channel, target = None, None
    if want_yt:
        if not yt.is_configured():
            return jsonify(error="YouTube posting isn't set up yet (README step 5)."), 400
        acct = yt.account(uid)
        if not acct["signed_in"]:
            return jsonify(error="Connect YouTube first, so Pit Crew knows which channel to post to.", signin="youtube"), 400
        channel = data.get("channel") or (acct.get("channel") or {}).get("id")
        if channel and channel not in {c["id"] for c in acct["channels"]}:
            return jsonify(error="That YouTube channel isn't connected any more. Pick a channel, then try again."), 400
    if want_ig:
        acct = ig.account(uid)
        if not acct.get("configured"):
            return jsonify(error="Instagram posting isn't set up yet: Pit Crew needs a Meta app (README step 6)."), 400
        target = next((a for a in acct.get("accounts", []) if a["ig_id"] == (data.get("ig_id") or acct.get("ig_id"))), None)
        if not target:
            return jsonify(error="Connect Instagram first.", signin="instagram"), 400
        if not target["can_post"]:
            return jsonify(error=f"@{target['username']} is a personal account, and Instagram only lets apps post to "
                                 "Business or Creator accounts. Switch it to professional in the Instagram app, "
                                 "then connect again."), 400

    # Only what isn't already on a platform goes to it.
    yt_rows = [(j, i) for j, i in rows if want_yt and not any(u["idx"] == i for u in jobs[j].get("uploads") or [])]
    ig_rows = [(j, i) for j, i in rows if want_ig and not any(p["idx"] == i and p["status"] in IG_BUSY
                                                              for p in jobs[j].get("ig_posts") or [])]
    if not yt_rows and not ig_rows:
        return jsonify(error="Those clips are already posted or planned there."), 400
    mode = data.get("schedule") if data.get("schedule") in ("now", "d18", "d12", "two", "custom") else "d18"
    try:
        every = int(data.get("every") or 24)
    except (TypeError, ValueError):
        every = 24
    order = list(dict.fromkeys(yt_rows + ig_rows))  # one slot per clip, shared by both platforms
    try:
        times = dict(zip(order, yt.plan_times(len(order), mode, data.get("tz"), data.get("start"), every)))
    except RuntimeError as e:
        return jsonify(error=str(e), field="start"), 400

    titles = {(str(r["job"]), int(r["idx"])): str(r.get("title") or "").strip()[:95] for r in data["items"]}
    started_yt = 0
    for jid in dict.fromkeys(j for j, _ in yt_rows):
        idxs = [i for j, i in yt_rows if j == jid]
        by_idx = {s["idx"]: s for s in jobs[jid]["shorts"]}
        items = [{**by_idx[i], "title": titles.get((jid, i)) or by_idx[i]["title"]} for i in idxs]
        with LOCK:
            if jid in POSTING:
                continue
            POSTING.add(jid)
            earlier = list(load_job(jid).get("uploads") or [])
        update(jid, upload_status="starting", upload_msg="Starting", uploads=earlier, upload_queue=idxs)
        threading.Thread(target=do_upload, args=(uid, jid, items, mode, [times[(jid, i)] for i in idxs], earlier, channel),
                         daemon=True).start()
        started_yt += len(items)

    now = datetime.now(timezone.utc)
    planned_ig = 0
    for jid in dict.fromkeys(j for j, _ in ig_rows):
        by_idx = {s["idx"]: s for s in jobs[jid]["shorts"]}
        new = []
        for j, i in ig_rows:
            if j != jid:
                continue
            t = times[(jid, i)]
            new.append({"idx": i, "title": titles.get((jid, i)) or by_idx[i]["title"],
                        "when": t.astimezone(timezone.utc).isoformat() if t and t > now else None,
                        "ig_id": target["ig_id"], "username": target["username"], "status": "waiting", "error": ""})

        def add(ps, new=new):
            live = {p["idx"] for p in ps if p["status"] in IG_BUSY}
            fresh = [n for n in new if n["idx"] not in live]
            return [p for p in ps if p["idx"] not in {n["idx"] for n in fresh}] + fresh
        _mutate(jid, add)
        DUE.add(jid)
        planned_ig += len(new)
    if planned_ig:
        _WAKE.set()
    return jsonify(ok=True, youtube=started_yt, instagram=planned_ig)


@app.post("/api/clips/<job_id>/<int:idx>/title")
def clip_title(job_id, idx):
    """Save a Short's title as the creator edits it (so scheduling it later, from any page, uses the new title)."""
    title = str((request.get_json(silent=True) or {}).get("title", "")).strip()[:95]
    if not title:
        return jsonify(error="Give the Short a title."), 400
    with LOCK:
        job = load_job(job_id)
        if not job or not any(s["idx"] == idx and not s.get("pending") for s in job.get("shorts", [])):
            return jsonify(error="That Short isn't available any more."), 404
    update_short(job_id, idx, title=title)
    return jsonify(ok=True)


@app.post("/api/clips/delete")
def clips_delete():
    """Delete draft Shorts (on neither YouTube nor Instagram, nor planned for either) and their files. Clips that
    aren't drafts are left alone and listed in "kept"."""
    uid, deleted, kept = g.user["id"], [], []
    for r in (request.get_json(force=True) or {}).get("items") or []:
        try:
            jid, idx = str(r["job"]), int(r["idx"])
        except (KeyError, TypeError, ValueError):
            continue
        with LOCK:
            job = load_job(jid)
            s = next((x for x in (job or {}).get("shorts", []) if x["idx"] == idx and not x.get("pending")), None)
            if not job or job.get("owner") != uid or not s:
                continue
            if not is_draft(job, s) or s.get("retrying") or jid in POSTING or job.get("upload_status") in UPLOADING:
                kept.append({"job": jid, "idx": idx, "title": s.get("title", "")})
                continue
            live = JOBS.get(jid) or job
            live["shorts"] = [x for x in live["shorts"] if x["idx"] != idx]
            (JOBS_DIR / jid / "job.json").write_text(json.dumps(live, default=str), encoding="utf-8")
        _remove(_short_files(JOBS_DIR / jid, s))
        deleted.append({"job": jid, "idx": idx})
    if not deleted and kept:
        return jsonify(error="Only drafts can be deleted here. Posted and scheduled clips stay.", kept=kept), 400
    return jsonify(ok=True, deleted=deleted, kept=kept)
