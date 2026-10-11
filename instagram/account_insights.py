"""
Instagram account analytics for the Analytics page's Instagram tab (Instagram API with Instagram Login, metrics
from Meta's /<IG_ID>/insights): reach day by day, views, accounts engaged, interactions, followers vs everyone else,
follows and unfollows, profile link taps, who the followers are (country, city, age, gender), and when they're
online. Meta keeps account numbers for 90 days and gives at most 30 days per request, so a longer window (up to 90
days) is asked in pieces of up to 30 days and added up. Counts (views, likes, comments, shares, saves, link taps,
follows) add up; "reach" and "accounts engaged" count each account once per piece, so over more than one piece they
can't be added and are left out (None). Demographics need 100+ followers; a metric Meta won't give is left out,
never an error.
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


KEEP_DAYS = 90  # how far back Meta keeps account numbers
ADDS = ("views", "likes", "comments", "shares", "saves", "profile_links_taps")


def ig_window(days=30, start=None, end=None):
    """(since, until, note) for the Instagram account numbers that match a page range: the last `days` days, or
    start..end (dates), cut to the last 90 days. note = "" (exact), "cut" (part of it is older than 90 days) or
    "old" (all of it is: nothing to show)."""
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    oldest = today - timedelta(days=KEEP_DAYS)
    if start and end:
        since = datetime.combine(start, datetime.min.time(), timezone.utc)
        until = datetime.combine(end, datetime.min.time(), timezone.utc) + timedelta(days=1)
    else:
        until, since = today, today - timedelta(days=max(1, min(int(days or 30), 3650)))
    until = min(until, today)
    if until <= oldest:
        return None, None, "old"
    note = "cut" if since < oldest else ""
    return max(since, oldest), until, note


def account_insights(user_id, days=30, start=None, end=None):
    """The Instagram account's numbers for the last `days` days or start..end (cut to the last 90 days), or None when
    Instagram isn't connected. Adds "days" (the length used), "since"/"until" (dates) and "note" ("", "cut", "old")."""
    info = load(user_id)
    if not info:
        return None
    since, until, note = ig_window(days, start, end)
    if note == "old":
        return {"days": 0, "note": "old", "totals": {}, "reach_daily": [], "reach_by": {}, "views_by": {}, "follows": {},
                "taps": {}, "online": {}, "followers": {}, "engaged": {}}
    key = (user_id, info.get("ig_id"), since.date(), until.date())
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < TTL:
        return {**hit[1], "note": note}  # the same window can come from a cut range ("a year") or an exact one
    tok, base, ig = info["token"], f"{GRAPH}/{API_VERSION}", info["ig_id"]
    pieces, s = [], since
    while s < until:
        e = min(s + timedelta(days=30), until)
        pieces.append({"since": int(s.timestamp()), "until": int(e.timestamp()), "period": "day"})
        s = e
    one = len(pieces) == 1
    totals_m = "views,reach,accounts_engaged,total_interactions,likes,comments,shares,saves,profile_links_taps"
    jobs = {"online": dict(metric="online_followers", period="lifetime")}
    for n, win in enumerate(pieces):
        jobs[f"series{n}"] = dict(metric="reach", metric_type="time_series", **win)
        jobs[f"totals{n}"] = dict(metric=totals_m, metric_type="total_value", **win)
        jobs[f"views_by{n}"] = dict(metric="views", metric_type="total_value", breakdown="follow_type", **win)
        jobs[f"follows{n}"] = dict(metric="follows_and_unfollows", metric_type="total_value", breakdown="follow_type", **win)
        jobs[f"taps{n}"] = dict(metric="profile_links_taps", metric_type="total_value", breakdown="contact_button_type", **win)
    if one:
        jobs["reach_by0"] = dict(metric="reach", metric_type="total_value", breakdown="follow_type", **pieces[0])
    for dim in ("country", "city", "age", "gender"):
        jobs["fol_" + dim] = dict(metric="follower_demographics", period="lifetime", metric_type="total_value",
                                  timeframe="this_month", breakdown=dim)
        jobs["eng_" + dim] = dict(metric="engaged_audience_demographics", period="lifetime", metric_type="total_value",
                                  timeframe="this_month", breakdown=dim)
    with ThreadPoolExecutor(6) as ex:
        got = dict(zip(jobs, ex.map(lambda p: _safe(_q, base, tok, ig, **p), jobs.values())))
    rng = range(len(pieces))
    series = []
    for n in rng:
        for r in got[f"series{n}"]:
            for v in r.get("values") or []:
                series.append({"day": (v.get("end_time") or "")[:10], "reach": v.get("value", 0)})

    def add(name, metric, fn):  # sum a breakdown or total over the pieces
        out = {}
        for n in rng:
            for k, v in fn(got[f"{name}{n}"], metric).items():
                out[k] = out.get(k, 0) + (v or 0)
        return out
    totals = {}
    for k in totals_m.split(","):
        vals = [_total(got[f"totals{n}"], k) for n in rng]
        totals[k] = (vals[0] if one else (sum(v for v in vals if v is not None) if k in ADDS and any(v is not None for v in vals) else None))
    online = {}
    for r in got["online"]:
        val = ((r.get("values") or [{}])[-1] or {}).get("value") or {}
        if isinstance(val, dict):
            online = {int(h): n for h, n in val.items() if str(h).isdigit()}
    out = {
        "days": (until - since).days, "since": since.date().isoformat(), "until": (until - timedelta(days=1)).date().isoformat(),
        "note": note,
        "totals": totals,
        "reach_daily": series,
        "reach_by": _breakdown(got["reach_by0"], "reach") if one else {},  # FOLLOWER / NON_FOLLOWER (one piece only)
        "views_by": add("views_by", "views", _breakdown),
        "follows": add("follows", "follows_and_unfollows", _breakdown),  # FOLLOWER = new follows, NON_FOLLOWER = unfollows
        "taps": add("taps", "profile_links_taps", _breakdown),
        "online": online,  # hour (UTC) -> followers online
        "followers": {d: _breakdown(got["fol_" + d], "follower_demographics") for d in ("country", "city", "age", "gender")},
        "engaged": {d: _breakdown(got["eng_" + d], "engaged_audience_demographics") for d in ("country", "city", "age", "gender")},
    }
    _CACHE[key] = (time.time(), out)
    return out


_FOLLOWS = {}  # (ig_id, since, hours) -> new followers in a finished window (never changes, so kept)


def follows_after(user_id, ig_id, posted_at, hours=48):
    """New followers the account got in the `hours` after `posted_at` (an aware datetime), as {"follows", "complete"};
    None when Instagram can't say (account not connected, or the window is older than the 90 days Meta keeps).
    Instagram doesn't tell which Reel brought a follower, so this is the account's new followers right after a Reel."""
    since = posted_at.astimezone(timezone.utc)
    until = since + timedelta(hours=hours)
    now = datetime.now(timezone.utc)
    if now - since > timedelta(days=88):
        return None
    key = (ig_id, int(since.timestamp()), hours)
    if key in _FOLLOWS:
        return _FOLLOWS[key]
    info = load(user_id, ig_id)
    if not info:
        return None
    rows = _safe(_q, f"{GRAPH}/{API_VERSION}", info["token"], ig_id, metric="follows_and_unfollows",
                 metric_type="total_value", breakdown="follow_type", period="day",
                 since=int(since.timestamp()), until=int(min(until, now).timestamp()))
    if not rows:
        return None
    got = _breakdown(rows, "follows_and_unfollows")
    out = {"follows": int(got.get("FOLLOWER", 0) or 0), "complete": until <= now}
    if out["complete"]:
        _FOLLOWS[key] = out
    return out
