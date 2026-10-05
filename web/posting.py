"""
Upload to YouTube: posts or schedules the ticked Shorts in the background.
"""
import os
import threading
import traceback

from flask import abort, g, jsonify, request

import pipeline
import youtube as yt
from settings import JOBS_DIR

from web.server import app
from web.store import JOBS, LOCK, load_job, update


POSTING = set()  # jobs whose Shorts are being uploaded right now (in this process)


def short_description(it, vlog, own_channel=None):
    """The Short's YouTube description: its hook (or title), a link to the full vlog, the channel as an
    @mention, and hashtags. Links in Shorts descriptions can't be tapped (YouTube's rule since 2023) but
    show and can be copied; @mentions can be tapped. The tappable link is "Related video" (set in Studio)."""
    tags = it.get("hashtags", [])
    lead = it.get("hook", "") if it.get("hook_mode", "text") != "none" else it.get("title", "")
    parts = [lead]
    vid = (vlog or {}).get("video_id")
    if not vid and (vlog or {}).get("youtube_url"):
        vid = yt.video_id_from_url(vlog["youtube_url"])
    if vid:
        parts.append(f"Watch the full video: https://www.youtube.com/watch?v={vid}")
    handle = (vlog or {}).get("channel_handle") or (own_channel or {}).get("handle") or ""
    name = (vlog or {}).get("channel") or (own_channel or {}).get("title") or ""
    if handle:
        parts.append(f"More from {handle}")
    elif name:
        parts.append(f"More from {name}")
    parts.append(" ".join("#" + t for t in tags + ["Shorts"]))
    return "\n\n".join(p for p in parts if p.strip())


def youtube_title(title):
    return title + " #Shorts" if "#shorts" not in title.lower() and len(title) <= 90 else title


def do_upload(user_id, job_id, items, mode, times, earlier):
    """Upload `items` at `times`. An item with "replace" (its earlier upload record) is an edited Short:
    the new version goes up first, then the old one is deleted, so a failure never loses both."""
    job_dir = JOBS_DIR / job_id
    results = list(earlier)
    try:
        update(job_id, upload_status="connecting", upload_msg="Connecting to YouTube")
        service = yt.get_service(user_id)
        own = yt.account(user_id).get("channel") or {}
        channel = own.get("id")
        with LOCK:
            vlog = dict((JOBS.get(job_id) or {}).get("vlog") or {})
        for k, (it, when) in enumerate(zip(items, times)):
            old = it.get("replace")
            label = (f"Uploading the new version of Short {it['idx']}" if old
                     else f"Uploading Short {k + 1} of {len(items)}")
            update(job_id, upload_status="uploading", upload_msg=label, upload_pct=0)
            tags = it.get("hashtags", [])
            desc = short_description(it, vlog, own)
            vid, note = yt.upload_short(
                service, upload_file(job_dir, it), youtube_title(it["title"]), desc, tags, when, job_dir / it["thumb"],
                progress=lambda p: update(job_id, upload_pct=p),
            )
            rec = {"idx": it["idx"], "title": it["title"], "video_id": vid, "video": it["video"],
                   "thumb": it["thumb"], "when": when.isoformat() if when else None, "note": note,
                   "channel": channel}
            if old:
                update(job_id, upload_msg="Removing the old version from YouTube")
                try:
                    yt.delete_video(service, old["video_id"])
                except Exception as e:
                    print("Couldn't delete the old version:", repr(e)[:300])
                    rec["note"] = ("The old version is still on YouTube: delete it in YouTube Studio. "
                                   + (note or "")).strip()
                results = [rec if r["idx"] == it["idx"] else r for r in results]
            else:
                results.append(rec)
            update(job_id, uploads=results)  # saved at once, so a retry never posts this Short twice
        done = "Updated" if all(i.get("replace") for i in items) else "All posted" if mode == "now" else "All scheduled"
        update(job_id, upload_status="done", upload_msg=done, uploads=results)
    except Exception as e:
        traceback.print_exc()
        msg = yt.upload_error_message(e)
        if results and not any(i.get("replace") for i in items):
            msg += f" ({len(results)} already on YouTube; pressing the button again posts only the rest.)"
        update(job_id, upload_status="error", upload_msg=msg, uploads=results)
    finally:
        with LOCK:
            POSTING.discard(job_id)


def upload_file(job_dir, it):
    """The Short with its thumbnail as the first frame (pipeline/cover.py), so the creator can pick it in
    the YouTube app; the plain Short if that can't be made or COVER_FRAME=0."""
    if os.getenv("COVER_FRAME", "1") != "0" and it.get("thumb"):
        try:
            return pipeline.covered_video(job_dir, it["video"], it["thumb"])
        except Exception as e:  # noqa: BLE001  (never fail an upload over the cover frame)
            print("Couldn't add the thumbnail as the first frame:", repr(e)[:300])
    return job_dir / it["video"]


@app.post("/api/schedule/<job_id>")
def schedule(job_id):
    data = request.get_json(force=True)
    with LOCK:
        job = load_job(job_id)
        if not job or job.get("status") != "ready":
            abort(400)
        if job_id in POSTING:
            return jsonify(error="These Shorts are already being posted."), 400
        by_idx = {s["idx"]: s for s in job["shorts"]}
        if any(s.get("retrying") for s in job["shorts"]):
            return jsonify(error="Wait until the Short you're remaking is ready."), 400
        earlier = list(job.get("uploads") or [])
    if not yt.is_configured():
        return jsonify(error="YouTube isn't connected yet: client_secret.json is missing. "
                             "The Shorts are saved in the jobs folder, so you can post them by hand, "
                             "or follow README step 5 to turn on automatic posting."), 400
    acct = yt.account(g.user["id"])
    if not acct["signed_in"]:
        return jsonify(error="Connect YouTube first, so Pit Crew knows which channel to post to.",
                       signin=True), 400
    posted = {u["idx"] for u in earlier}
    items = []
    for row in data.get("shorts", []):
        s = by_idx.get(int(row["idx"]))
        if s and row.get("keep") and s["idx"] not in posted:
            items.append({**s, "title": (row.get("title") or s["title"]).strip()[:95]})
    if not items:
        return jsonify(error="Those Shorts are already on YouTube." if posted else "Tick at least one Short."), 400
    mode = data.get("schedule", job.get("schedule", "d18"))
    if mode not in ("now", "d18", "d12", "two", "custom"):
        mode = "d18"
    try:
        every = int(data.get("every") or 24)
    except (TypeError, ValueError):
        every = 24
    try:
        times = yt.plan_times(len(items), mode, data.get("tz"), data.get("start"), every)
    except RuntimeError as e:
        return jsonify(error=str(e), field="start"), 400
    with LOCK:
        if job_id in POSTING:
            return jsonify(error="These Shorts are already being posted."), 400
        POSTING.add(job_id)
    update(job_id, upload_status="starting", upload_msg="Starting", uploads=earlier, schedule=mode)
    threading.Thread(target=do_upload, args=(g.user["id"], job_id, items, mode, times, earlier), daemon=True).start()
    return jsonify(ok=True)
