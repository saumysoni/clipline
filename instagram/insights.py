"""
Instagram numbers for Analytics: the account, its recent Reels and each Reel's views, reach, likes,
comments, shares, saves and watch time. Cached for 10 minutes per user.
"""
import time
from concurrent.futures import ThreadPoolExecutor

from instagram.config import API_VERSION, GRAPH
from instagram.connection import account, load
from instagram.http import InstagramError, call

REEL_METRICS = "views,reach,likes,comments,shares,saved,total_interactions,ig_reels_avg_watch_time"
_CACHE = {}
TTL = 600


def _reel_numbers(base, tok, m):
    row = {"id": m["id"], "caption": (m.get("caption") or "").split("\n")[0][:120], "permalink": m.get("permalink", ""),
           "thumb": m.get("thumbnail_url", ""), "when": m.get("timestamp", ""),
           "likes": m.get("like_count", 0) or 0, "comments": m.get("comments_count", 0) or 0}
    try:
        data = call("GET", f"{base}/{m['id']}/insights", {"metric": REEL_METRICS, "access_token": tok}).get("data", [])
        for d in data:
            v = (d.get("values") or [{}])[0].get("value", d.get("total_value", {}).get("value", 0))
            row[d["name"]] = v or 0
    except InstagramError as e:
        row["error"] = str(e)
    row.setdefault("views", 0)
    row["avg_watch_s"] = round((row.pop("ig_reels_avg_watch_time", 0) or 0) / 1000, 1)
    return row


def dashboard(user_id, clipline_ids=(), limit=30):
    """{"account", "totals", "reels"} for this user's recent Reels, or None when not connected."""
    hit = _CACHE.get(user_id)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    info = load(user_id)
    if not info:
        return None
    tok, base = info["token"], f"{GRAPH}/{API_VERSION}"
    acct = account(user_id)
    try:
        prof = call("GET", f"{base}/me", {"fields": "followers_count,media_count", "access_token": tok})
        acct.update(followers=prof.get("followers_count"), media_count=prof.get("media_count"))
    except InstagramError:
        pass
    media = call("GET", f"{base}/{info['ig_id']}/media",
                 {"fields": "id,caption,media_type,media_product_type,permalink,thumbnail_url,timestamp,"
                            "like_count,comments_count", "limit": 50, "access_token": tok}).get("data", [])
    reels = [m for m in media if m.get("media_product_type") == "REELS"][:limit]
    with ThreadPoolExecutor(6) as ex:
        rows = list(ex.map(lambda m: _reel_numbers(base, tok, m), reels))
    ids = set(clipline_ids)
    for r in rows:
        r["clipline"] = r["id"] in ids
    keys = ("views", "reach", "likes", "comments", "shares", "saved")
    totals = {k: sum(int(r.get(k) or 0) for r in rows) for k in keys}
    totals["reels"] = len(rows)
    out = {"account": acct, "totals": totals,
           "reels": sorted(rows, key=lambda r: -(r.get("views") or 0)),
           "partial": any("error" in r for r in rows)}
    _CACHE[user_id] = (time.time(), out)
    return out


def forget(user_id):
    _CACHE.pop(user_id, None)
