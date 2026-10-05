"""
Analytics for the creator's Shorts: one call gathers everything the Analytics page shows.

Two sources:
  - YouTube Analytics API (scope yt-analytics.readonly, "YouTube Analytics API" enabled in Google Cloud):
    views, likes, comments, shares, subscribers, watch time, % viewed, day by day, top Shorts, how viewers
    found them, who they are and where, and per Short the audience-retention curve. Its numbers are
    about 2 days behind. creatorContentType==SHORTS keeps it to Shorts, so every Short on the channel
    counts, not only Pit Crew's.
  - YouTube Data API (the posting scope): live view/like/comment counts, titles, thumbnails, lengths.
If the analytics part isn't allowed (an older connection, or the API isn't enabled), the page still gets
the live counts and a note saying how to unlock the rest.
"""
import re
import threading
import time
from datetime import date, datetime, timedelta

from youtube.connection import load_creds


SHORTS = "creatorContentType==SHORTS"
CACHE_SECS = 600  # YouTube's numbers change slowly; don't ask again for 10 minutes
_CACHE, _LOCK = {}, threading.Lock()


class NeedsReconnect(Exception):
    """The connection can't read analytics: connect YouTube again (and enable the API)."""


def _services(user_id):
    from googleapiclient.discovery import build

    creds = load_creds(user_id)
    if not creds:
        raise RuntimeError("Your YouTube channel isn't connected. Click Connect YouTube, then try again.")
    return (build("youtube", "v3", credentials=creds, cache_discovery=False),
            build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False))


def _report(ya, start, end, metrics, dimensions=None, filters=SHORTS, sort=None, max_results=None):
    """Rows as dicts ({"day": "2026-10-01", "views": 120, ...}). Raises NeedsReconnect when not allowed."""
    from googleapiclient.errors import HttpError

    q = {"ids": "channel==MINE", "startDate": str(start), "endDate": str(end), "metrics": metrics}
    for k, v in (("dimensions", dimensions), ("filters", filters), ("sort", sort), ("maxResults", max_results)):
        if v:
            q[k] = v
    try:
        resp = ya.reports().query(**q).execute()
    except HttpError as e:
        if e.resp.status in (401, 403):
            raise NeedsReconnect(str(e)) from e
        raise
    names = [h["name"] for h in resp.get("columnHeaders", [])]
    return [dict(zip(names, row)) for row in resp.get("rows") or []]


def _try(fn, *a, **k):
    """A report that may not be available for every channel (e.g. demographics need enough viewers)."""
    try:
        return fn(*a, **k)
    except NeedsReconnect:
        raise
    except Exception as e:  # noqa: BLE001
        print("Analytics report skipped:", repr(e)[:200])
        return []


def _seconds(iso):
    """ISO 8601 duration (PT1M5S) -> seconds."""
    m = re.fullmatch(r"P(?:\d+D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    return (int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)) if m else 0


def _videos(yt3, ids):
    """Title, thumbnail, publish time, length and live counts for video ids."""
    out = {}
    ids = [i for i in dict.fromkeys(ids) if i]
    for k in range(0, len(ids), 50):
        resp = yt3.videos().list(part="snippet,statistics,contentDetails", id=",".join(ids[k:k + 50])).execute()
        for it in resp.get("items", []):
            sn, st = it.get("snippet", {}), it.get("statistics", {})
            th = sn.get("thumbnails") or {}
            out[it["id"]] = {
                "id": it["id"], "title": sn.get("title", ""), "published": sn.get("publishedAt"),
                "thumb": (th.get("high") or th.get("medium") or th.get("default") or {}).get("url", ""),
                "secs": _seconds((it.get("contentDetails") or {}).get("duration")),
                "live_views": int(st.get("viewCount", 0)), "live_likes": int(st.get("likeCount", 0)),
                "live_comments": int(st.get("commentCount", 0))}
    return out


TOTALS = ("views,likes,comments,shares,subscribersGained,subscribersLost,estimatedMinutesWatched,"
          "averageViewDuration,averageViewPercentage")


def _totals(ya, start, end):
    rows = _report(ya, start, end, TOTALS)
    t = rows[0] if rows else {}
    views = t.get("views", 0) or 0
    eng = (t.get("likes", 0) or 0) + (t.get("comments", 0) or 0) + (t.get("shares", 0) or 0)
    return {"views": views, "likes": t.get("likes", 0), "comments": t.get("comments", 0),
            "shares": t.get("shares", 0), "subs": (t.get("subscribersGained", 0) or 0) - (t.get("subscribersLost", 0) or 0),
            "watch_hours": round((t.get("estimatedMinutesWatched", 0) or 0) / 60, 1),
            "avg_secs": round(t.get("averageViewDuration", 0) or 0, 1),
            "avg_pct": round(t.get("averageViewPercentage", 0) or 0, 1),
            "engagement": round(100 * eng / views, 2) if views else 0}


def dashboard(user_id, days=28, clipline_ids=()):
    """Everything for the Analytics page, for the last `days` days (0 = since the channel started)."""
    key = (user_id, days)
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and time.time() - hit[0] < CACHE_SECS:
            return hit[1]
    yt3, ya = _services(user_id)
    end = date.today()
    start = end - timedelta(days=days - 1) if days else date(2005, 4, 23)
    prev_end, prev_start = start - timedelta(days=1), start - timedelta(days=days) if days else None
    clip = set(clipline_ids)
    out = {"range": {"start": str(start), "end": str(end), "days": days}, "notes": [], "full": True}
    ch = (yt3.channels().list(part="snippet,statistics", mine=True).execute().get("items") or [{}])[0]
    out["channel"] = {"title": (ch.get("snippet") or {}).get("title", ""),
                      "subscribers": int((ch.get("statistics") or {}).get("subscriberCount", 0) or 0),
                      "thumb": (((ch.get("snippet") or {}).get("thumbnails") or {}).get("default") or {}).get("url", "")}
    try:
        out["totals"] = _totals(ya, start, end)
        out["previous"] = _totals(ya, prev_start, prev_end) if prev_start else None
        out["daily"] = [{"day": r["day"], "views": r.get("views", 0), "likes": r.get("likes", 0),
                         "subs": (r.get("subscribersGained", 0) or 0) - (r.get("subscribersLost", 0) or 0)}
                        for r in _try(_report, ya, start, end, "views,likes,subscribersGained,subscribersLost",
                                      "day", sort="day")]
        top = _try(_report, ya, start, end, "views,likes,comments,shares,averageViewPercentage,"
                   "averageViewDuration,subscribersGained", "video", sort="-views", max_results=50)
        meta = _videos(yt3, [r["video"] for r in top] + list(clip))
        out["shorts"] = [{**meta.get(r["video"], {"id": r["video"], "title": "", "thumb": ""}),
                          "views": r.get("views", 0), "likes": r.get("likes", 0), "comments": r.get("comments", 0),
                          "shares": r.get("shares", 0), "avg_pct": round(r.get("averageViewPercentage", 0) or 0, 1),
                          "avg_secs": round(r.get("averageViewDuration", 0) or 0, 1),
                          "subs": r.get("subscribersGained", 0), "clipline": r["video"] in clip} for r in top]
        out["traffic"] = [{"source": r["insightTrafficSourceType"], "views": r.get("views", 0)}
                          for r in _try(_report, ya, start, end, "views", "insightTrafficSourceType", sort="-views")]
        out["countries"] = [{"code": r["country"], "views": r.get("views", 0)}
                            for r in _try(_report, ya, start, end, "views", "country", sort="-views", max_results=8)]
        demo = _try(_report, ya, start, end, "viewerPercentage", "ageGroup,gender", filters=None)
        ages, genders = {}, {}
        for r in demo:
            ages[r["ageGroup"]] = ages.get(r["ageGroup"], 0) + r["viewerPercentage"]
            genders[r["gender"]] = genders.get(r["gender"], 0) + r["viewerPercentage"]
        out["ages"] = [{"group": a.replace("age", "").replace("-", "–"), "pct": round(p, 1)} for a, p in sorted(ages.items())]
        out["genders"] = [{"gender": g, "pct": round(p, 1)} for g, p in sorted(genders.items(), key=lambda x: -x[1])]
    except NeedsReconnect:
        out["full"] = False
        out["notes"].append("reconnect")
        meta = _videos(yt3, list(clip))
        out["shorts"] = sorted(({**m, "views": m["live_views"], "likes": m["live_likes"],
                                 "comments": m["live_comments"], "clipline": True} for m in meta.values()),
                               key=lambda s: -s["views"])
        t = {k: sum(s.get(k, 0) for s in out["shorts"]) for k in ("views", "likes", "comments")}
        out["totals"] = {**t, "engagement": round(100 * (t["likes"] + t["comments"]) / t["views"], 2) if t["views"] else 0}
        out["previous"] = None
    out["insights"] = insights(out)
    with _LOCK:
        _CACHE[key] = (time.time(), out)
    return out


def short_detail(user_id, video_id, days=28):
    """One Short: day-by-day views, the audience-retention curve and how viewers found it."""
    yt3, ya = _services(user_id)
    end = date.today()
    meta = _videos(yt3, [video_id]).get(video_id, {})
    start = end - timedelta(days=days - 1) if days else \
        (datetime.fromisoformat(meta["published"].replace("Z", "+00:00")).date() if meta.get("published") else date(2005, 4, 23))
    f = f"video=={video_id}"
    out = {"short": meta, "full": True}
    try:
        out["daily"] = [{"day": r["day"], "views": r.get("views", 0)}
                        for r in _report(ya, start, end, "views", "day", filters=f, sort="day")]
        out["retention"] = [{"at": round(r["elapsedVideoTimeRatio"] * 100, 1), "watching": round(r["audienceWatchRatio"] * 100, 1),
                             "vs_similar": r.get("relativeRetentionPerformance")}
                            for r in _try(_report, ya, start, end, "audienceWatchRatio,relativeRetentionPerformance",
                                          "elapsedVideoTimeRatio", filters=f + ";audienceType==ORGANIC")]
        out["traffic"] = [{"source": r["insightTrafficSourceType"], "views": r.get("views", 0)}
                          for r in _try(_report, ya, start, end, "views", "insightTrafficSourceType", filters=f, sort="-views")]
        tot = _try(_report, ya, start, end, "views,likes,comments,shares,averageViewPercentage,averageViewDuration,"
                   "subscribersGained", filters=f)
        out["totals"] = tot[0] if tot else {}
    except NeedsReconnect:
        out["full"] = False
    return out


def insights(d):
    """A few plain-English takeaways computed from the numbers (no AI, no guessing)."""
    tips, shorts, t = [], [s for s in d.get("shorts", []) if s.get("views")], d.get("totals") or {}
    if shorts:
        best = shorts[0]
        tips.append({"kind": "best", "text": f"Your top Short is “{best['title']}” with {best['views']:,} views"
                     + (f", watched for {best['avg_pct']:.0f}% of its length on average." if best.get("avg_pct") else ".")})
    if t.get("views") and t.get("subs"):
        tips.append({"kind": "subs", "text": f"You gain {1000 * t['subs'] / t['views']:.1f} subscribers per 1,000 Shorts views."})
    prev = d.get("previous") or {}
    if prev.get("views") and t.get("views") is not None:
        ch = 100 * (t["views"] - prev["views"]) / prev["views"]
        tips.append({"kind": "trend", "text": f"Views are about the same as the {d['range']['days']} days before."
                     if abs(ch) < 1 else f"Views are {'up' if ch > 0 else 'down'} {abs(ch):.0f}% on the "
                     f"{d['range']['days']} days before."})
    timed = [s for s in shorts if s.get("secs")]
    if len(timed) >= 6:  # which length works best (only with enough Shorts to compare)
        buckets = {"under 30 seconds": (0, 30), "30 to 45 seconds": (30, 45), "45 to 60 seconds": (45, 61),
                   "over a minute": (61, 10**6)}
        avg = {name: [s["views"] for s in timed if lo <= s["secs"] < hi] for name, (lo, hi) in buckets.items()}
        avg = {k: sum(v) / len(v) for k, v in avg.items() if len(v) >= 2}
        if len(avg) >= 2:
            name = max(avg, key=avg.get)
            tips.append({"kind": "length", "text": f"Your Shorts of {name} get the most views on average ({avg[name]:,.0f})."})
    dated = [s for s in shorts if s.get("published")]
    if len(dated) >= 8:
        by_day = {}
        for s in dated:
            wd = datetime.fromisoformat(s["published"].replace("Z", "+00:00")).strftime("%A")
            by_day.setdefault(wd, []).append(s["views"])
        by_day = {k: sum(v) / len(v) for k, v in by_day.items() if len(v) >= 2}
        if len(by_day) >= 2:
            day = max(by_day, key=by_day.get)
            tips.append({"kind": "day", "text": f"Shorts published on a {day} do best for you ({by_day[day]:,.0f} views on average)."})
    if d.get("traffic"):
        total = sum(r["views"] for r in d["traffic"]) or 1
        shorts_feed = sum(r["views"] for r in d["traffic"] if r["source"] == "SHORTS")
        tips.append({"kind": "feed", "text": f"{100 * shorts_feed / total:.0f}% of your Shorts views come from the Shorts feed."})
    return tips
