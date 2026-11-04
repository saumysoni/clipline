"""
The Reels on a creator's Instagram account, posted with Pit Crew or not (Shorts & Reels lists them with an Instagram link;
web/instagram_reels.py). Only the text a list needs and Instagram's picture address are read, never the video.
"""
from instagram.config import API_VERSION, GRAPH
from instagram.connection import load
from instagram.http import InstagramError, call

MAX_REELS = 500
MAX_PAGES = 20  # an account's posts come mixed (photos too), 50 at a time
TITLE_MAX = 100


def title_of(caption):
    """The caption's first line, the nearest thing a Reel has to a title. The rest of the caption isn't kept."""
    line = next((x.strip() for x in (caption or "").splitlines() if x.strip()), "")
    return (line[:TITLE_MAX - 3].rstrip() + "...") if len(line) > TITLE_MAX else (line or "Instagram Reel")


def account_reels(user_id, ig_id):
    """This account's Reels, newest first: [{id, title, published, permalink, thumb}]. Raises InstagramError."""
    info = load(user_id, ig_id)
    if not info:
        raise InstagramError("Your Instagram connection has expired. Click Connect Instagram, then try again.")
    out, after = [], None
    for _ in range(MAX_PAGES):
        params = {"fields": "id,caption,media_product_type,permalink,thumbnail_url,timestamp", "limit": 50, "access_token": info["token"]}
        if after:
            params["after"] = after
        page = call("GET", f"{GRAPH}/{API_VERSION}/{info['ig_id']}/media", params)
        out += [{"id": str(m["id"]), "title": title_of(m.get("caption")), "published": m.get("timestamp", ""),
                 "permalink": m.get("permalink", ""), "thumb": m.get("thumbnail_url", "")}
                for m in page.get("data", []) if m.get("media_product_type") == "REELS"]
        paging = page.get("paging") or {}
        after = (paging.get("cursors") or {}).get("after")
        if len(out) >= MAX_REELS or not after or not paging.get("next"):
            break
    return out[:MAX_REELS]
