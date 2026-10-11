"""
More YouTube analytics for the Analytics page, on top of youtube/analytics.py: the Compare tab (any videos side by
side, day by day, with every number YouTube Studio's advanced mode shows), the Audience tab (devices, playback
location, search terms, sharing services, cities) and the vlog -> Shorts link (how many viewers
a vlog's Shorts sent to it). Same rules as analytics.py: everything comes from the YouTube Analytics API (about
2 days behind) for the active channel, cached 10 minutes, and a report YouTube refuses is left out, never an error.
"""
import threading
import time
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor

from accounts import db
import youtube.analytics as base
from youtube.analytics import CACHE_SECS, CONTENT, NeedsReconnect, _report, _try, _videos, _with_engaged

_CACHE, _LOCK = {}, threading.Lock()

# Every number the Compare table can show (YouTube Analytics metric names).
VIDEO_METRICS = ("views,likes,comments,shares,subscribersGained,subscribersLost,estimatedMinutesWatched,"
                 "averageViewDuration,averageViewPercentage")


def _cached(key, fn):
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and time.time() - hit[0] < CACHE_SECS:
            return hit[1]
    out = fn()
    with _LOCK:
        _CACHE[key] = (time.time(), out)
    return out


def _per_thread(user_id):
    """A getter for a YouTube Analytics client of this thread's own. Google's client (httplib2) must never be shared
    between threads: a shared one can hang or mix up answers, so each worker of a ThreadPoolExecutor builds its own."""
    local = threading.local()

    def get():
        if not hasattr(local, "ya"):
            local.ya = base._services(user_id)[1]
        return local.ya
    return get


def _chan(user_id):
    return (db.connection(user_id, "youtube") or {}).get("account_id")


def _row(r, meta):
    m = meta.get(r["video"], {"id": r["video"], "title": "", "thumb": ""})
    return {**m, "views": r.get("views", 0), "engaged": r.get("engagedViews"), "likes": r.get("likes", 0),
            "comments": r.get("comments", 0), "shares": r.get("shares", 0),
            "subs": (r.get("subscribersGained", 0) or 0) - (r.get("subscribersLost", 0) or 0),
            "minutes": round(r.get("estimatedMinutesWatched", 0) or 0, 1),
            "avg_secs": round(r.get("averageViewDuration", 0) or 0, 1),
            "avg_pct": round(r.get("averageViewPercentage", 0) or 0, 1)}


def videos(user_id, start, end, content="shorts", clipline_ids=(), live=False):
    """Every video with views in the period (up to 200, most viewed first), plus Pit Crew's Shorts posted by then
    (at 0 if they had none), each with all the Compare numbers, plus the period's totals. The page works out each
    video's share of the total. live (All time): views, likes and comments are YouTube's live counts, the same
    numbers the Overview and YouTube Studio show (Analytics is ~2 days behind)."""
    flt = CONTENT.get(content, CONTENT["shorts"])
    clip = set(clipline_ids)

    def build():
        yt3, ya = base._services(user_id)
        rows = _with_engaged(ya, start, end, VIDEO_METRICS, "video", filters=flt, sort="-views", max_results=200)
        meta = _videos(yt3, [r["video"] for r in rows] + (list(clip) if content in ("shorts", "all") else []))
        shown = {r["video"] for r in rows}
        if content in ("shorts", "all"):  # Pit Crew's Shorts with no views in this period: listed at 0, so they can be ticked
            rows = rows + [{"video": v} for v in sorted(clip) if v in meta and v not in shown
                           and (meta[v].get("published") or "")[:10] <= str(end)]
        vids = [{**_row(r, meta), "clipline": r["video"] in clip} for r in rows]
        if live:
            for v in vids:
                m = meta.get(v["id"]) or {}
                v.update(views=max(v["views"], m.get("live_views", 0)), likes=m.get("live_likes", v["likes"]),
                         comments=m.get("live_comments", v["comments"]))
            vids.sort(key=lambda v: -v["views"])
        keys = ("views", "engaged", "likes", "comments", "shares", "subs", "minutes")
        listed = {k: sum((v.get(k) or 0) for v in vids) for k in keys}
        # The total is the channel's (the same number as the Overview), not the sum of the list: views on videos
        # that are deleted, private or not listed any more still count in YouTube's totals. That part is "other".
        ch = (_with_engaged(ya, start, end, "views,likes,comments,shares,subscribersGained,subscribersLost,"
                            "estimatedMinutesWatched", filters=flt) or [{}])[0]
        total = {"views": ch.get("views", 0), "engaged": ch.get("engagedViews"), "likes": ch.get("likes", 0),
                 "comments": ch.get("comments", 0), "shares": ch.get("shares", 0),
                 "subs": (ch.get("subscribersGained", 0) or 0) - (ch.get("subscribersLost", 0) or 0),
                 "minutes": round(ch.get("estimatedMinutesWatched", 0) or 0, 1)}
        for k in keys:  # never below what the list adds up to (live counts can be ahead of Analytics)
            if total[k] is not None:
                total[k] = max(total[k], listed[k])
        if not any(v.get("engaged") is not None for v in vids):
            total["engaged"] = None
        other = {k: (round(total[k] - listed[k], 1) if total[k] is not None else None) for k in keys}
        return {"videos": vids, "total": total, "other": other if (other["views"] or 0) > 0 else None}
    return _cached(("videos", user_id, _chan(user_id), str(start), str(end), content, tuple(sorted(clip)), live), build)


def compare(user_id, ids, start, end):
    """Day-by-day views (and engaged views where YouTube gives them) for up to 8 videos, for the Compare chart."""
    ids = [i for i in dict.fromkeys(ids) if i][:8]

    def one(get, vid):
        rows = _try(_with_engaged, get(), start, end, "views", "day", filters=f"video=={vid}", sort="day")
        return vid, {r["day"]: {"views": r.get("views", 0), "engaged": r.get("engagedViews")} for r in rows}

    def build():
        base._services(user_id)  # signs in (and refreshes the token) once, before the workers start
        get = _per_thread(user_id)
        with ThreadPoolExecutor(4) as ex:
            got = dict(ex.map(lambda v: one(get, v), ids))
        return {"series": [{"id": v, "days": got.get(v, {})} for v in ids]}
    return _cached(("compare", user_id, _chan(user_id), str(start), str(end), tuple(ids)), build)


DEVICE = {"MOBILE": "Phone", "DESKTOP": "Computer", "TABLET": "Tablet", "TV": "TV", "GAME_CONSOLE": "Game console",
          "UNKNOWN_PLATFORM": "Other"}
PLAYBACK = {"SHORTS_FEED": "Shorts feed", "SHORTS": "Shorts feed", "WATCH": "YouTube watch page", "CHANNEL": "Your channel page",
            "EMBEDDED": "Other websites", "BROWSE": "Home and browse", "SEARCH": "Search results",
            "YT_OTHER": "Other YouTube pages", "EXTERNAL_APP": "Other apps", "MOBILE": "YouTube mobile site",
            "UNKNOWN": "Other"}
OS = {"ANDROID": "Android", "IOS": "iOS", "WINDOWS": "Windows", "MACINTOSH": "macOS", "LINUX": "Linux",
      "CHROMECAST": "Chromecast", "SMART_TV": "Smart TV", "PLAYSTATION": "PlayStation", "XBOX": "Xbox",
      "NINTENDO_3DS": "Nintendo", "WII": "Nintendo", "ROKU": "Roku", "TIZEN": "Samsung TV", "WEBOS": "LG TV",
      "FIREFOX": "Firefox OS", "KAIOS": "KaiOS", "DOCOMO": "Docomo", "BLACKBERRY": "BlackBerry", "OTHER": "Other",
      "UNKNOWN": "Other"}


SUBSCRIBED = {"SUBSCRIBED": "Subscribers", "UNSUBSCRIBED": "Not subscribed"}
SUB_RETRY = 24 * 3600  # after YouTube refuses "subscribers vs not" for a channel, ask again a day later
_SUB_REFUSED = {}      # channel id -> time YouTube last refused it


def _subscribed(get, start, end, flt, chan):
    """Views from subscribers vs everyone else, or None when YouTube won't give it. YouTube answers HTTP 500 for
    subscribedStatus on some channels (a real one, Oct 2026, whatever the metric), so after a refusal Pit Crew
    waits a day before asking that channel again instead of failing on every load."""
    if time.time() - _SUB_REFUSED.get(chan, 0) < SUB_RETRY:
        return None
    try:
        got = _report(get(), start, end, "views", "subscribedStatus", filters=flt)
    except NeedsReconnect:
        raise
    except Exception as e:  # noqa: BLE001
        print("YouTube refused subscribers vs not; asking again in 24 h:", repr(e)[:160])
        _SUB_REFUSED[chan] = time.time()
        return None
    return [{"key": r["subscribedStatus"], "label": SUBSCRIBED.get(r["subscribedStatus"], r["subscribedStatus"]),
             "views": r.get("views", 0)} for r in got if r.get("views")]


def audience(user_id, start, end, content="shorts"):
    """The Audience tab's breakdowns. Each is a list of {"key", "label", "views"} (sharing: "shares"); a breakdown
    YouTube won't give for this channel (too few viewers, or not offered for Shorts) is an empty list."""
    flt = CONTENT.get(content, CONTENT["shorts"])

    def rows(get, metric, dim, labels=None, max_results=None, extra=None):
        f = ";".join(x for x in (flt, extra) if x) or None
        got = _try(_report, get(), start, end, metric, dim, filters=f, sort="-" + metric.split(",")[0], max_results=max_results)
        return [{"key": r[dim], "label": (labels or {}).get(r[dim]) or (str(r[dim]).replace("_", " ").capitalize() if labels else r[dim]), metric.split(",")[0]: r.get(metric.split(",")[0], 0),
                 **({"minutes": round(r.get("estimatedMinutesWatched", 0) or 0)} if "estimatedMinutesWatched" in metric else {})}
                for r in got]

    def build():
        base._services(user_id)  # signs in (and refreshes the token) once, before the workers start
        get = _per_thread(user_id)
        jobs = {
            "devices": ("views", "deviceType", DEVICE, None, None),
            "os": ("views", "operatingSystem", OS, 8, None),
            "playback": ("views", "insightPlaybackLocationType", PLAYBACK, None, None),
            "sharing": ("shares", "sharingService", None, 8, None),
            "search": ("views", "insightTrafficSourceDetail", None, 25, "insightTrafficSourceType==YT_SEARCH"),
            "cities": ("views", "city", None, 10, None),
        }
        out = {}
        with ThreadPoolExecutor(4) as ex:
            sub = ex.submit(_subscribed, get, start, end, flt, _chan(user_id))
            futs = {k: ex.submit(rows, get, *v) for k, v in jobs.items()}
            for k, f in futs.items():
                try:
                    out[k] = f.result()
                except NeedsReconnect:
                    raise
                except Exception as e:  # noqa: BLE001
                    print("Audience report skipped:", k, repr(e)[:160])
                    out[k] = []
            out["subscribed"] = sub.result()  # None = YouTube didn't give it (the page shows the card waiting)
        return out
    return _cached(("audience", user_id, _chan(user_id), str(start), str(end), content), build)


CLIP_METRICS = "views,likes,comments,shares,subscribersGained,subscribersLost,averageViewPercentage,averageViewDuration"


def clip_totals(user_id, ids):
    """Every number of these videos since they were posted, for the YouTube-vs-Instagram charts: views, likes and
    comments are YouTube's live counts (what Studio shows; Analytics is ~2 days behind), shares, subscribers and
    % viewed come from Analytics. Only videos on the active channel get Analytics numbers; the rest get live counts.
    {video id: {...}}"""
    ids = [i for i in dict.fromkeys(ids) if i]

    def build():
        yt3, ya = base._services(user_id)
        meta = _videos(yt3, ids)
        start = min((date.fromisoformat(m["published"][:10]) for m in meta.values() if m.get("published")),
                    default=date.today()) - timedelta(days=1)
        rows = {}
        for k in range(0, len(ids), 200):  # a video== filter takes up to 500 ids; stay well under
            for r in _try(_with_engaged, ya, start, date.today(), CLIP_METRICS, "video",
                          filters="video==" + ",".join(ids[k:k + 200]), sort="-views", max_results=200):
                rows[r["video"]] = r
        out = {}
        for v in ids:
            m, r = meta.get(v), rows.get(v, {})
            if not m:
                continue  # deleted or on another account
            out[v] = {"views": max(r.get("views", 0) or 0, m.get("live_views", 0)), "likes": m.get("live_likes", 0),
                      "comments": m.get("live_comments", 0), "shares": r.get("shares"),
                      "subs": (r.get("subscribersGained", 0) or 0) - (r.get("subscribersLost", 0) or 0) if r else None,
                      "engaged": r.get("engagedViews"),
                      "avg_pct": round(r["averageViewPercentage"], 1) if r.get("averageViewPercentage") else None,
                      "avg_secs": round(r["averageViewDuration"], 1) if r.get("averageViewDuration") else None,
                      "title": m.get("title", ""), "thumb": m.get("thumb", ""), "secs": m.get("secs"), "published": m.get("published")}
        return out
    return _cached(("clips", user_id, _chan(user_id), tuple(ids)), build)


def vlog_links(user_id, vlogs, start, end):
    """For vlogs Pit Crew uploaded (vlogs = [{"video_id", "title", "shorts": [video ids]}]): the vlog's views, its
    Shorts' views, and how many views the vlog got from Shorts' related-video links (traffic source
    SHORTS_CONTENT_LINKS), i.e. viewers the Shorts sent to it."""
    def build():
        yt3, ya = base._services(user_id)
        out = []
        for v in vlogs:
            vid = v["video_id"]
            tot = _try(_report, ya, start, end, "views,estimatedMinutesWatched", filters=f"video=={vid}")
            src = _try(_report, ya, start, end, "views", "insightTrafficSourceType", filters=f"video=={vid}")
            sent = sum(r.get("views", 0) for r in src if r.get("insightTrafficSourceType") == "SHORTS_CONTENT_LINKS")
            sv = 0
            if v.get("shorts"):
                rows = _try(_report, ya, start, end, "views", "video", filters="video==" + ",".join(v["shorts"][:200]))
                sv = sum(r.get("views", 0) for r in rows)
            meta = _videos(yt3, [vid]).get(vid, {})
            out.append({"video_id": vid, "title": meta.get("title") or v.get("title", ""), "thumb": meta.get("thumb", ""),
                        "views": (tot[0] if tot else {}).get("views", 0),
                        "minutes": round((tot[0] if tot else {}).get("estimatedMinutesWatched", 0) or 0),
                        "shorts": len(v.get("shorts") or []), "shorts_views": sv, "sent": sent})
        return out
    key = tuple((v["video_id"], tuple(v.get("shorts") or ())) for v in vlogs)
    return _cached(("vlogs", user_id, _chan(user_id), str(start), str(end), key), build)
