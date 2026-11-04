"""
Reels on the creator's Instagram accounts that Pit Crew didn't post (instagram/reels.py): they show on Shorts & Reels, marked
"Made outside Pit Crew", with a link to Instagram. What Pit Crew posted has its own records and cards, so it's left out.

Read when an account is connected (web/first_import.py), then at most once a day: the daily upkeep, or when the page opens and
the list is older. Instagram's picture addresses stop working after a while, so a daily read also keeps them fresh. Everything
kept here goes when the connection does (db.drop_connection): Disconnect, an expired sign-in, or removal through Meta.
"""
import threading
import time
import traceback

import instagram as ig
from accounts import db

from web.vlogs import user_jobs

DAY = 24 * 3600
RETRY = 3600  # seconds before a page opening asks again after a read that failed
_RUNNING, _TRIED = set(), {}


def _own_ids(user_id):
    return {str(p["media_id"]) for job in user_jobs(user_id) for p in job.get("ig_posts") or [] if p.get("media_id")}


def refresh_account(user_id, ig_id, now=None):
    """Read one account's Reels. Any Instagram error changes nothing."""
    try:
        own = _own_ids(user_id)
        rows = [r for r in ig.account_reels(user_id, ig_id) if r["id"] not in own]
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return False
    if not db.connection(user_id, "instagram", ig_id):  # disconnected while reading: keep nothing
        return False
    db.replace_instagram_reels(user_id, ig_id, rows)
    db.set_channel_checked(user_id, ig_id, now or time.time())
    return True


def refresh_user(user_id, now=None):
    for row in db.connections(user_id, "instagram"):
        if row["account_id"]:
            refresh_account(user_id, row["account_id"], now)


def refresh_if_old(user_id, now=None):
    """When the page opens: read in the background only if a list is a day old, and not more than once per RETRY when
    reads keep failing (an account never read counts as old, and Instagram's limits are per account)."""
    now = now or time.time()
    old = [r["account_id"] for r in db.connections(user_id, "instagram") if r["account_id"]
           and now - (db.channel_checked(user_id, r["account_id"]) or 0) >= DAY]
    if not old or user_id in _RUNNING or now - _TRIED.get(user_id, 0) < RETRY:
        return
    _TRIED[user_id] = now

    def run():
        try:
            refresh_user(user_id)
        finally:
            _RUNNING.discard(user_id)
    _RUNNING.add(user_id)
    threading.Thread(target=run, daemon=True).start()


def running(user_id):
    return user_id in _RUNNING


def reel_items(user_id):
    """In the shape of web/channel_videos.py's items, for the same cards."""
    own = _own_ids(user_id)
    return [{"id": r["media_id"], "platform": "instagram", "title": r["title"], "published": r["published"].replace("+0000", "Z"), "seconds": 0, "short": True,
             "privacy": "public", "gone": False, "url": r["permalink"] if r["permalink"].startswith("https://www.instagram.com/") else "",
             "thumb": r["thumb"] if r["thumb"].startswith("https://") else ""}
            for r in db.instagram_reel_rows(user_id) if r["media_id"] not in own]
