"""
Instagram account analytics for the Analytics page's Instagram tab (Instagram API with Instagram Login, metrics
from Meta's /<IG_ID>/insights): reach day by day, views, accounts engaged, interactions, followers vs everyone else,
follows and unfollows, profile link taps, who the followers are (country, city, age, gender), and when they're
online. Meta keeps account numbers for 90 days and gives at most 30 days per request, so the tab shows the last
7 or 30 days. Demographics need 100+ followers; a metric Meta won't give is left out, never an error.
"""
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from instagram.config import API_VERSION, GRAPH
from instagram.connection import load
from instagram import http
from instagram.http import InstagramError

_CACHE, TTL = {}, 600


def _q(base, tok, ig_id, **params):
    return http.call("GET", f"{base}/{ig_id}/insights", {**params, "access_token": tok}).get("data", [])


def _total(rows, name):
    for r in rows:
        if r.get("name") == name:
            return (r.get("total_value") or {}).get("value")
    return None


def _breakdown(rows, name):
    """{dimension value: count} from a total_value metric asked with one breakdown."""
    out = {}
    for r in rows:
        if r.get("name") != name:
            continue
        for b in (r.get("total_value") or {}).get("breakdowns") or []:
            for res in b.get("results") or []:
                out[",".join(res.get("dimension_values") or [])] = res.get("value", 0)
    return out


def _safe(fn, *a, **k):
    try:
        return fn(*a, **k)
    except InstagramError as e:
        print("Instagram insight skipped:", k.get("metric"), k.get("breakdown", ""), str(e)[:160])
        return []
    except Exception as e:  # noqa: BLE001
        print("Instagram insight skipped:", repr(e)[:160])
        return []


def account_insights(user_id, days=30):
    """The Instagram tab's numbers for the active account over the last `days` days (7 or 30), or None when
    Instagram isn't connected."""
    days = 7 if days and days <= 7 else 30
    info = load(user_id)
    if not info:
        return None
    key = (user_id, info.get("ig_id"), days)
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    tok, base, ig = info["token"], f"{GRAPH}/{API_VERSION}", info["ig_id"]
    until = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    since = until - timedelta(days=days)
    win = {"since": int(since.timestamp()), "until": int(until.timestamp()), "period": "day"}
    totals_m = "views,reach,accounts_engaged,total_interactions,likes,comments,shares,saves,profile_links_taps"
    jobs = {
        "series": dict(metric="reach", metric_type="time_series", **win),
        "totals": dict(metric=totals_m, metric_type="total_value", **win),
        "reach_by": dict(metric="reach", metric_type="total_value", breakdown="follow_type", **win),
        "views_by": dict(metric="views", metric_type="total_value", breakdown="follow_type", **win),
        "follows": dict(metric="follows_and_unfollows", metric_type="total_value", breakdown="follow_type", **win),
        "taps": dict(metric="profile_links_taps", metric_type="total_value", breakdown="contact_button_type", **win),
        "online": dict(metric="online_followers", period="lifetime"),
    }
    for dim in ("country", "city", "age", "gender"):
        jobs["fol_" + dim] = dict(metric="follower_demographics", period="lifetime", metric_type="total_value",
                                  timeframe="this_month", breakdown=dim)
        jobs["eng_" + dim] = dict(metric="engaged_audience_demographics", period="lifetime", metric_type="total_value",
                                  timeframe="this_month", breakdown=dim)
    with ThreadPoolExecutor(6) as ex:
        got = dict(zip(jobs, ex.map(lambda p: _safe(_q, base, tok, ig, **p), jobs.values())))
    series = []
    for r in got["series"]:
        for v in r.get("values") or []:
            series.append({"day": (v.get("end_time") or "")[:10], "reach": v.get("value", 0)})
    t = got["totals"]
    online = {}
    for r in got["online"]:
        val = ((r.get("values") or [{}])[-1] or {}).get("value") or {}
        if isinstance(val, dict):
            online = {int(h): n for h, n in val.items() if str(h).isdigit()}
    out = {
        "days": days,
        "totals": {k: _total(t, k) for k in totals_m.split(",")},
        "reach_daily": series,
        "reach_by": _breakdown(got["reach_by"], "reach"),  # FOLLOWER / NON_FOLLOWER
        "views_by": _breakdown(got["views_by"], "views"),
        "follows": _breakdown(got["follows"], "follows_and_unfollows"),  # FOLLOWER = new follows, NON_FOLLOWER = unfollows
        "taps": _breakdown(got["taps"], "profile_links_taps"),
        "online": online,  # hour (UTC) -> followers online
        "followers": {d: _breakdown(got["fol_" + d], "follower_demographics") for d in ("country", "city", "age", "gender")},
        "engaged": {d: _breakdown(got["eng_" + d], "engaged_audience_demographics") for d in ("country", "city", "age", "gender")},
    }
    _CACHE[key] = (time.time(), out)
    return out
