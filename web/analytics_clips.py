"""
Analytics, "Your clips" part: every Short Pit Crew posted, with the views it got in its first 7 days on YouTube and
on Instagram (a fair way to compare a new clip with older ones), and "What's working": what Pit Crew knows about
each clip (hook style, length, posting time, vlog) set against those numbers. No AI, no guessing: a takeaway is only
shown when there are enough clips behind it.

Instagram only reports running totals, so each Reel's numbers are saved once a day (instagram.snapshot_reels) and
"first 7 days" comes from those saved days.
"""
import os
import re
import threading
import time
import traceback
from datetime import date, datetime, timedelta, timezone

from flask import g, jsonify, request

import instagram as ig
import youtube as yt
from accounts import db
from settings import JOBS_DIR

from web.server import app
from web.store import LOCK, load_job
from web.vlogs import user_jobs

MIN_CLIPS = 4       # posted clips (with first-week numbers) before any takeaway is shown
MIN_GROUP = 2       # clips in each group being compared
MIN_LIFT = 1.2      # the difference worth mentioning (20%)
HOOKS = {"curiosity": "Curiosity hooks", "bold": "Bold hooks", "story": "Story hooks", "custom": "Your own hooks",
         "none": "Shorts with no hook banner"}


def _dt(iso):
    return datetime.fromisoformat(iso) if iso else None


def posted_clips(user_id, vlog=""):
    """Every Pit Crew Short this user posted (oldest first), with where and when."""
    out = []
    for job in user_jobs(user_id):
        if vlog and job["id"] != vlog:
            continue
        name = (job.get("vlog") or {}).get("title") or job.get("name") or "Your vlog"
        ups = {u["idx"]: u for u in job.get("uploads") or []}
        reels = {p["idx"]: p for p in job.get("ig_posts") or [] if p["status"] == "done" and p.get("media_id")}
        for s in job.get("shorts", []):
            u, p = ups.get(s["idx"]), reels.get(s["idx"])
            yt_at = _dt(u.get("when") or u.get("uploaded_at")) if u else None
            if u and yt_at and yt_at > datetime.now(timezone.utc):
                u, yt_at = None, None  # scheduled, not out yet
            ig_at = _dt(p.get("posted_at")) if p else None
            if not (u and u.get("video_id")) and not p:
                continue
            first = min(t for t in (yt_at, ig_at) if t) if (yt_at or ig_at) else None
            out.append({"job": job["id"], "idx": s["idx"], "title": s.get("title", ""), "vlog": name,
                        "thumb": s.get("thumb", ""), "length": round((s.get("end") or 0) - (s.get("start") or 0)),
                        "hook": "none" if s.get("hook_mode") == "none" else (s.get("hook_style") or "custom"),
                        "posted_at": first.isoformat() if first else None,
                        "youtube": {"video_id": u["video_id"], "at": yt_at.isoformat() if yt_at else None,
                                    "channel": u.get("channel")} if u and u.get("video_id") else None,
                        "instagram": {"media_id": p["media_id"], "at": ig_at.isoformat() if ig_at else None,
                                      "ig_id": p.get("ig_id"), "permalink": p.get("permalink", ""),
                                      "username": p.get("username", "")} if p else None})
    out.sort(key=lambda c: c["posted_at"] or "")
    return out


def _ig_first_week(snaps, posted):
    """Views after 7 days from the saved daily rows: (views, complete) or (None, False) without enough history."""
    if not snaps or not posted:
        return None, False
    target = (posted + timedelta(days=7)).date()
    near = [n for day, n in snaps if target <= date.fromisoformat(day) <= target + timedelta(days=2)]
    if near:  # a saved day just after its first week
        return near[0].get("views", 0), True
    if (datetime.now(timezone.utc) - posted).days < 7:
        return snaps[-1][1].get("views", 0), False  # still in its first week: counting
    return None, False  # saving started after its first week


def add_numbers(user_id, clips):
    vids = [{"id": c["youtube"]["video_id"], "channel": c["youtube"]["channel"],
             "published": _dt(c["youtube"]["at"]).date() if c["youtube"]["at"] else date.today()}
            for c in clips if c["youtube"]]
    try:
        week = yt.first_week_views(user_id, vids) if vids else {}
    except Exception:  # noqa: BLE001  (YouTube trouble shouldn't hide Instagram numbers)
        traceback.print_exc()
        week = {}
    posts = [{"media_id": c["instagram"]["media_id"], "ig_id": c["instagram"]["ig_id"]} for c in clips if c["instagram"]]
    try:
        ig.snapshot_reels(user_id, posts)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    snaps = db.reel_snapshots(user_id, [p["media_id"] for p in posts])
    for c in clips:
        if c["youtube"]:
            w = week.get(c["youtube"]["video_id"]) or {}
            c["youtube"].update(first7=w.get("views"), complete=bool(w.get("complete")))
        if c["instagram"]:
            v, done = _ig_first_week(snaps.get(c["instagram"]["media_id"]), _dt(c["instagram"]["at"]))
            c["instagram"].update(first7=v, complete=done)
    return clips


def _bucket_length(n):
    return "under 20 seconds" if n < 20 else "20–35 seconds" if n < 35 else "35–50 seconds" if n < 50 else "over 50 seconds"


def _bucket_time(iso):
    t = _dt(iso)
    if not t or t.utcoffset() in (None, timedelta(0)):
        return None  # only times saved with the creator's own time zone say anything about their day
    h = t.hour
    return "in the morning" if 5 <= h < 12 else "in the afternoon" if h < 17 else "in the evening" if h < 22 else "at night"


def _compare(clips, plat, key, label, what):
    groups = {}
    for c in clips:
        k = key(c)
        if k:
            groups.setdefault(k, []).append(c[plat]["first7"])
    groups = {k: v for k, v in groups.items() if len(v) >= MIN_GROUP}
    if len(groups) < 2:
        return None
    avg = {k: sum(v) / len(v) for k, v in groups.items()}
    best, worst = max(avg, key=avg.get), min(avg, key=avg.get)
    if avg[worst] <= 0 or avg[best] / avg[worst] < MIN_LIFT:
        return None
    n = sum(len(v) for v in groups.values())
    other = label(worst)
    other = other[0].lower() + other[1:]  # "clips from "Bali"", keeping names' capitals
    return {"kind": what, "text": f"{label(best)} get {avg[best] / avg[worst]:.1f}× the first-week views of {other}",
            "basis": f"{n} {'Shorts' if plat == 'youtube' else 'Reels'}"}


def takeaways(clips, plat):
    """What's working on one platform, from clips whose first week is over."""
    done = [c for c in clips if c[plat] and c[plat].get("complete") and c[plat].get("first7") is not None]
    if len(done) < MIN_CLIPS:
        return {"ready": False, "have": len(done), "need": MIN_CLIPS}
    tips = [
        _compare(done, plat, lambda c: c["hook"], lambda k: HOOKS.get(k, k.title() + " hooks"), "hook"),
        _compare(done, plat, lambda c: _bucket_length(c["length"]), lambda k: "Clips " + k + " long", "length"),
        _compare(done, plat, lambda c: _bucket_time(c[plat]["at"]), lambda k: "Clips posted " + k, "time"),
        _compare(done, plat, lambda c: c["vlog"], lambda k: f"Clips from \"{k}\"", "vlog"),
    ]
    best = max(done, key=lambda c: c[plat]["first7"])
    tips.append({"kind": "best", "text": f"Your strongest start: \"{best['title']}\" with "
                                         f"{best[plat]['first7']:,} views in its first week", "basis": ""})
    return {"ready": True, "tips": [t for t in tips if t]}


@app.get("/api/analytics/clips")
def analytics_clips():
    vlog = request.args.get("vlog", "")
    vlog = vlog if re.fullmatch(r"[0-9a-f]{10}", vlog) else ""
    clips = add_numbers(g.user["id"], posted_clips(g.user["id"], vlog))
    return jsonify(clips=clips, youtube=takeaways(clips, "youtube"), instagram=takeaways(clips, "instagram"))


def _snapshot_all():
    """Once every few hours: save today's numbers for every Pit Crew Reel (so no day is missed when nobody opens
    Analytics). In the cloud this becomes a scheduled job."""
    time.sleep(120)
    while True:
        try:
            owners = {}
            for path in JOBS_DIR.glob("*/job.json"):
                if not re.fullmatch(r"[0-9a-f]{10}", path.parent.name) or '"media_id"' not in path.read_text(encoding="utf-8"):
                    continue
                with LOCK:
                    job = load_job(path.parent.name)
                for p in (job or {}).get("ig_posts") or []:
                    if p["status"] == "done" and p.get("media_id") and job.get("owner"):
                        owners.setdefault(job["owner"], []).append({"media_id": p["media_id"], "ig_id": p.get("ig_id")})
            for uid, posts in owners.items():
                ig.snapshot_reels(uid, posts)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        time.sleep(6 * 3600)


if os.getenv("RETENTION_OFF") != "1":  # (also off in tests)
    threading.Thread(target=_snapshot_all, daemon=True, name="reel-snapshots").start()
