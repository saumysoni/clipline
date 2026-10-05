"""
Post to Instagram: the creator picks Instagram's own schedule (or "same as YouTube"); Pit Crew keeps the
plan in job["ig_posts"] and a background thread posts each Reel when its time comes (Instagram has no
scheduling for apps). Posts that came due while Pit Crew was closed go out when it starts again.

job["ig_posts"]: [{"idx", "title", "video", "thumb", "when" (ISO or None = now), "status", "media_id",
"permalink", "error"}]; status is waiting, posting, done, error, or check (Pit Crew stopped mid-post:
the creator checks Instagram before trying again, so nothing is posted twice).
"""
import json
import re
import threading

import traceback
from datetime import datetime, timezone

from flask import g, jsonify, request

import instagram as ig
import youtube as yt
from pipeline.cover import COVER_SECS
from settings import JOBS_DIR

from web.posting import upload_file
from web.server import app
from web.store import JOBS, LOCK, load_job

MODES = ("now", "d18", "d12", "two", "custom")
DUE = set()  # job ids with Reels waiting to be posted
_WAKE = threading.Event()


def _mutate(job_id, fn):
    """Change job["ig_posts"] in one step under LOCK (the scheduler thread and the page both change it)."""
    with LOCK:
        job = load_job(job_id)
        job["ig_posts"] = fn(list(job.get("ig_posts") or []))
        (JOBS_DIR / job_id / "job.json").write_text(json.dumps(job, default=str), encoding="utf-8")
        return list(job["ig_posts"])


def _edit(job_id, idx, **kw):
    return _mutate(job_id, lambda posts: [dict(p, **kw) if p["idx"] == idx else p for p in posts])


def _due(p):
    return p["status"] == "waiting" and (not p.get("when") or datetime.fromisoformat(p["when"]) <= datetime.now(timezone.utc))


def _post_one(job_id, p):
    with LOCK:
        job = load_job(job_id)
        owner, vlog = job.get("owner"), dict(job.get("vlog") or {})
        s = next((x for x in job.get("shorts", []) if x["idx"] == p["idx"]), None)
    claimed = []

    def claim(ps):  # only if it's still waiting (not cancelled in the meantime)
        out = []
        for x in ps:
            if x["idx"] == p["idx"] and x["status"] == "waiting":
                claimed.append(x)
                x = dict(x, status="posting", error="", step="Starting")
            out.append(x)
        return out
    _mutate(job_id, claim)
    if not claimed:
        return
    p = claimed[0]
    try:
        if not s:
            raise ig.InstagramError("This Short was removed from the job.")
        video = upload_file(JOBS_DIR / job_id, s)
        caption = ig.caption_for({**s, "title": p.get("title") or s["title"]}, vlog)
        out = ig.post_reel(owner, video, caption, cover_ms=int(COVER_SECS * 500),
                           progress=lambda m: _edit(job_id, p["idx"], step=m))
        _edit(job_id, p["idx"], status="done", step="", posted_at=datetime.now(timezone.utc).isoformat(), **out)
        ig.forget_insights(owner)
    except ig.InstagramError as e:
        _edit(job_id, p["idx"], status="error", step="", error=str(e))
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        _edit(job_id, p["idx"], status="error", step="", error="Something went wrong while posting. Try again.")


def _loop():
    while True:
        for job_id in list(DUE):
            with LOCK:
                job = load_job(job_id)
                posts = list((job or {}).get("ig_posts") or [])
            if not any(p["status"] == "waiting" for p in posts):
                DUE.discard(job_id)
                continue
            for p in posts:
                if _due(p):
                    _post_one(job_id, p)
        _WAKE.wait(30)
        _WAKE.clear()


def _startup():
    """Find waiting Reels in saved jobs; mark ones that were mid-post when Pit Crew stopped."""
    for path in JOBS_DIR.glob("*/job.json"):
        try:
            if '"ig_posts"' not in path.read_text(encoding="utf-8"):
                continue
            with LOCK:
                job = load_job(path.parent.name)
                posts = list((job or {}).get("ig_posts") or [])
            if not posts:
                continue
            if any(p["status"] == "posting" for p in posts):
                _mutate(job["id"], lambda ps: [dict(p, status="check", step="", error=(
                    "Pit Crew stopped while posting this. Check Instagram: if the Reel isn't there, press Try again."))
                    if p["status"] == "posting" else p for p in ps])
            if any(p["status"] == "waiting" for p in posts):
                DUE.add(job["id"])
        except Exception:  # noqa: BLE001
            traceback.print_exc()
    _loop()


threading.Thread(target=_startup, daemon=True, name="instagram-scheduler").start()


def _times(data, items, job):
    """When each item goes out on Instagram: aware datetimes or None (now)."""
    mode = data.get("schedule", "same")
    if mode == "same":  # the YouTube time if it's already on YouTube, else the YouTube card's schedule
        ups = {u["idx"]: u for u in job.get("uploads") or []}
        mode = data.get("yt_schedule") if data.get("yt_schedule") in MODES else job.get("schedule", "d18")
        planned = yt.plan_times(len(items), mode, data.get("tz"), data.get("yt_start"), _every(data.get("yt_every")))
        out = []
        for it, t in zip(items, planned):
            u = ups.get(it["idx"])
            out.append(datetime.fromisoformat(u["when"]) if u and u.get("when") else None if u else t)
        return out
    if mode not in MODES:
        mode = "d18"
    return yt.plan_times(len(items), mode, data.get("tz"), data.get("start"), _every(data.get("every")))


def _every(v):
    try:
        return int(v or 24)
    except (TypeError, ValueError):
        return 24


@app.post("/api/instagram/schedule/<job_id>")
def instagram_schedule(job_id):
    data = request.get_json(force=True)
    acct = ig.account(g.user["id"])
    if not acct.get("configured"):
        return jsonify(error="Instagram posting isn't set up yet: Pit Crew needs a Meta app (README step 6)."), 400
    if not acct.get("signed_in"):
        return jsonify(error="Connect Instagram first.", signin=True), 400
    if not acct.get("can_post"):
        return jsonify(error="Instagram only lets apps post to Business or Creator accounts. In the Instagram app: "
                             "Settings › Account type and tools › Switch to professional account (free), then "
                             "connect again.", switch=True), 400
    with LOCK:
        job = load_job(job_id)
        if not job or job.get("status") != "ready":
            return jsonify(error="These Shorts aren't ready yet."), 400
        by_idx = {s["idx"]: s for s in job["shorts"]}
        posts = list(job.get("ig_posts") or [])
        job = json.loads(json.dumps(job, default=str))
    busy = ("waiting", "posting", "done", "check")
    taken = {p["idx"] for p in posts if p["status"] in busy}
    items = []
    for row in data.get("shorts", []):
        s = by_idx.get(int(row["idx"]))
        if s and row.get("keep") and s["idx"] not in taken:
            items.append({"idx": s["idx"], "title": (row.get("title") or s["title"]).strip()[:95]})
    if not items:
        return jsonify(error="Those Shorts are already on Instagram or waiting to go." if taken
                       else "Tick at least one Short."), 400
    try:
        times = _times(data, items, job)
    except RuntimeError as e:
        return jsonify(error=str(e), field="start"), 400
    now = datetime.now(timezone.utc)
    new = [{**it, "when": t.astimezone(timezone.utc).isoformat() if t and t > now else None,
            "status": "waiting", "error": ""} for it, t in zip(items, times)]

    def add(ps):
        live = {p["idx"] for p in ps if p["status"] in busy}  # planned in another tab meanwhile
        fresh = [n for n in new if n["idx"] not in live]
        return [p for p in ps if p["idx"] not in {n["idx"] for n in fresh}] + fresh
    posts = _mutate(job_id, add)
    DUE.add(job_id)
    _WAKE.set()
    return jsonify(ok=True, ig_posts=posts)


def _change(job_id, idx, allowed, **kw):
    ok = []

    def fn(posts):
        p = next((x for x in posts if x["idx"] == idx), None)
        if not p or p["status"] not in allowed:
            return posts
        ok.append(True)
        if kw.get("drop"):
            return [x for x in posts if x["idx"] != idx]
        return [dict(x, **kw) if x["idx"] == idx else x for x in posts]
    posts = _mutate(job_id, fn)
    if not ok:
        return jsonify(error="That can't be changed now (it may be posting).", ig_posts=posts), 400
    if not kw.get("drop"):
        DUE.add(job_id)
        _WAKE.set()
    return jsonify(ok=True, ig_posts=posts)


@app.post("/api/instagram/cancel/<job_id>/<int:idx>")
def instagram_cancel(job_id, idx):
    return _change(job_id, idx, ("waiting", "error", "check"), drop=True)


@app.post("/api/instagram/retry/<job_id>/<int:idx>")
def instagram_retry(job_id, idx):
    return _change(job_id, idx, ("error", "check"), status="waiting", when=None, error="")


def clipline_reel_ids(user_id):
    """Instagram ids of the Reels Pit Crew posted for this user (for Analytics)."""
    ids = []
    for path in JOBS_DIR.glob("*/job.json"):
        if not re.fullmatch(r"[0-9a-f]{10}", path.parent.name):
            continue
        with LOCK:
            job = JOBS.get(path.parent.name) or load_job(path.parent.name)
        if job and job.get("owner") == user_id:
            ids += [p["media_id"] for p in job.get("ig_posts") or [] if p.get("media_id")]
    return ids




@app.get("/api/instagram/posts")
def instagram_posts():
    """Every Reel Pit Crew posted or planned for this user, newest vlog first (for the Scheduled page)."""
    uid, out = g.user["id"], []
    for path in sorted(JOBS_DIR.glob("*/job.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        if not re.fullmatch(r"[0-9a-f]{10}", path.parent.name) or '"ig_posts"' not in path.read_text(encoding="utf-8"):
            continue
        with LOCK:
            job = load_job(path.parent.name)
            if not job or job.get("owner") != uid:
                continue
            job = json.loads(json.dumps(job, default=str))
        shorts = {s["idx"]: s for s in job.get("shorts", [])}
        vlog = (job.get("vlog") or {}).get("title") or job.get("name") or "Your vlog"
        for p in job.get("ig_posts") or []:
            s = shorts.get(p["idx"], {})
            out.append({**p, "job": job["id"], "vlog": vlog, "thumb": s.get("thumb", ""),
                        "title": p.get("title") or s.get("title", "")})
    return jsonify(items=out, account=ig.account(uid))
