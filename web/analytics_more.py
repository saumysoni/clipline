"""
More of the Analytics page (youtube/analytics_more.py, instagram/account_insights.py): the Compare tab (every video
in the period with all its numbers, any of them day by day, and a CSV download), the Audience tab, the Instagram
account tab, the vlog -> Shorts link and the "this week" summary. Also `period_args()`, the range every analytics
route reads: ?days=7|28|90|365|0, or ?start=YYYY-MM-DD&end=YYYY-MM-DD, and ?content=shorts|videos|all.
"""
import csv
import io
import re
import traceback
from datetime import date

from flask import Response, g, jsonify, request

import instagram as ig
import youtube as yt
from instagram.account_insights import account_insights
from youtube.analytics import period
from youtube import analytics_more as more

from web.server import app
from web.vlogs import user_jobs


def period_args():
    """(start, end, content) from the query: a custom start..end (capped to today, at most 3 years), else the
    last `days` days."""
    content = request.args.get("content", "shorts")
    content = content if content in ("shorts", "videos", "all") else "shorts"
    try:
        s, e = date.fromisoformat(request.args.get("start", "")), date.fromisoformat(request.args.get("end", ""))
        e = min(e, date.today())
        if s <= e and (e - s).days <= 3 * 366:
            return s, e, content, None
    except ValueError:
        pass
    try:
        d = int(request.args.get("days", 28))
    except ValueError:
        d = 28
    d = d if d in (0, 7, 28, 90, 365) else 28
    start, end, _, _, _ = period(d)
    return start, end, content, d


def _err(e):
    from googleapiclient.errors import HttpError

    from web.analytics import _plain
    traceback.print_exc()
    if isinstance(e, (HttpError, RuntimeError)):
        return jsonify(error=_plain(e) if isinstance(e, HttpError) else str(e)), 502
    return jsonify(error="Couldn't load these numbers right now. Try Refresh in a minute."), 502


def _clip_ids(uid):
    from web.on_youtube import posted_shorts
    return [u["video_id"] for u in posted_shorts(uid) if u.get("video_id")]


@app.get("/api/analytics/videos")
def analytics_videos():
    if not yt.account(g.user["id"])["signed_in"]:
        return jsonify(connected=False)
    start, end, content, _ = period_args()
    try:
        d = more.videos(g.user["id"], start, end, content, _clip_ids(g.user["id"]))
        return jsonify({**d, "range": {"start": str(start), "end": str(end)}, "content": content})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@app.get("/api/analytics/videos.csv")
def analytics_videos_csv():
    start, end, content, _ = period_args()
    try:
        d = more.videos(g.user["id"], start, end, content, _clip_ids(g.user["id"]))
    except Exception as e:  # noqa: BLE001
        return _err(e)
    buf = io.StringIO()
    w = csv.writer(buf)
    cols = [("Title", "title"), ("Video ID", "id"), ("Published", "published"), ("Length (s)", "secs"),
            ("Views", "views"), ("Engaged views", "engaged"), ("Likes", "likes"), ("Comments", "comments"),
            ("Shares", "shares"), ("Subscribers", "subs"), ("Watch time (min)", "minutes"),
            ("Avg. view (s)", "avg_secs"), ("Avg. % viewed", "avg_pct"), ("Made with Pit Crew", "clipline")]
    w.writerow([c[0] for c in cols])
    for v in d["videos"]:
        w.writerow(["" if v.get(k) is None else v.get(k) for _, k in cols])
    name = f"pit-crew-{content}-{start}-to-{end}.csv"
    return Response(buf.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/analytics/compare")
def analytics_compare():
    ids = [i for i in request.args.get("ids", "").split(",") if re.fullmatch(r"[\w-]{6,20}", i)]
    if not ids:
        return jsonify(series=[])
    start, end, _, _ = period_args()
    try:
        return jsonify(more.compare(g.user["id"], ids, start, end))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@app.get("/api/analytics/audience")
def analytics_audience():
    if not yt.account(g.user["id"])["signed_in"]:
        return jsonify(connected=False)
    start, end, content, _ = period_args()
    try:
        return jsonify(more.audience(g.user["id"], start, end, content))
    except Exception as e:  # noqa: BLE001
        return _err(e)


def _vlogs(uid):
    """Vlogs on the creator's channel that have Shorts: uploaded with Pit Crew (vlog.video_id) or linked by URL."""
    out = []
    for j in user_jobs(uid):
        v = j.get("vlog") or {}
        vid = v.get("video_id") or yt.video_id_from_url(v.get("youtube_url") or "")
        shorts = [u["video_id"] for u in j.get("uploads") or [] if u.get("video_id")]
        if vid and shorts:
            out.append({"video_id": vid, "title": v.get("title") or j.get("name", ""), "shorts": shorts, "job": j["id"]})
    return out


@app.get("/api/analytics/vlogs")
def analytics_vlogs():
    uid = g.user["id"]
    if not yt.account(uid)["signed_in"]:
        return jsonify(items=[])
    start, end, _, _ = period_args()
    vlogs = _vlogs(uid)
    if not vlogs:
        return jsonify(items=[])
    try:
        rows = more.vlog_links(uid, vlogs, start, end)
        jobs = {v["video_id"]: v["job"] for v in vlogs}
        return jsonify(items=[{**r, "job": jobs.get(r["video_id"])} for r in rows if r["views"] or r["shorts_views"]])
    except Exception as e:  # noqa: BLE001
        return _err(e)


@app.get("/api/analytics/instagram")
def analytics_instagram_account():
    try:
        d = int(request.args.get("days", 30))
    except ValueError:
        d = 30
    try:
        out = account_insights(g.user["id"], d)
    except ig.InstagramError as e:
        return jsonify(error=str(e)), 502
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return jsonify(error="Couldn't load your Instagram account numbers. Try Refresh."), 502
    return jsonify(connected=out is not None, **(out or {}))


@app.get("/api/analytics/week")
def analytics_week():
    """This week at a glance: YouTube (all videos) and Instagram over the last 7 days, against the 7 before."""
    uid = g.user["id"]
    out = {}
    if yt.account(uid)["signed_in"]:
        try:
            d = yt.analytics_dashboard(uid, 7, _clip_ids(uid), content="all")
            t, p = d.get("totals") or {}, d.get("previous") or {}
            best = next((s for s in d.get("shorts") or [] if s.get("views")), None)
            out["youtube"] = {"views": t.get("views"), "prev": p.get("views"), "subs": t.get("subs"),
                              "watch_hours": t.get("watch_hours"), "full": d.get("full"),
                              "best": {"title": best.get("title"), "views": best.get("views"), "id": best.get("id")} if best else None}
        except Exception:  # noqa: BLE001
            traceback.print_exc()
    try:
        a = account_insights(uid, 7)
        if a:
            out["instagram"] = {"views": a["totals"].get("views"), "reach": a["totals"].get("reach"),
                                "follows": a["follows"].get("FOLLOWER")}
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    return jsonify(out)
