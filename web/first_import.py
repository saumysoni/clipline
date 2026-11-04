"""
The first time a YouTube channel or Instagram account is connected, Pit Crew brings in what's already on it, and the page
waits on a "Getting your dashboard ready" screen (js/first-import.js) until that's done. New accounts first get a Connect your
accounts screen, right after the email is confirmed; it's optional and shown until they connect something or skip.

"The first time" = Pit Crew has never finished reading that account (db.channel_checked): connecting it again while its list is
still kept doesn't wait. A failed read leaves it unread, so the usual daily read picks it up. The work is the same as the daily
read (web/channel_videos.py, web/instagram_reels.py), just started as soon as the account is connected. What's shown while it
runs is kept in memory only: after a restart the page simply goes on, and the daily read still fills the lists.
"""
import threading
import time
import traceback

import instagram as ig
from instagram.connection import is_professional
import youtube as yt
from accounts import db
from flask import g, jsonify

import web.channel_videos as CV
import web.instagram_reels as IR
from web.server import app

KEEP = 10 * 60  # seconds a finished import is still reported, for a page that comes back to it (popups blocked)
STUCK = 30 * 60  # seconds after which a read that never answered is forgotten
PLATFORMS = ("youtube", "instagram")
_LOCK = threading.Lock()
_IMPORTS = {}  # user id -> {(platform, account id): {"state": running / done / error, "name", counts, "at", "seen"}}


def _name(row):
    if row["platform"] == "instagram":
        name = (row["token"] or {}).get("username") or (row["profile"] or {}).get("username") or ""
        return "@" + name if name else "your Instagram account"
    return (row["profile"] or {}).get("title") or "your YouTube channel"


def _counts(uid, platform, account):
    if platform == "instagram":
        return {"reels": len(db.instagram_reel_rows(uid, account))}
    rows = [r for r in db.channel_video_rows(uid) if r["channel"] == account and r["gone_at"] is None]
    return {"videos": sum(not r["is_short"] for r in rows), "shorts": sum(bool(r["is_short"]) for r in rows)}


def _run(uid, platform, account, entry):
    try:
        ok = CV.refresh_channel(uid, account) if platform == "youtube" else IR.refresh_account(uid, account)
        if ok:
            entry.update(_counts(uid, platform, account))
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        ok = False
    with _LOCK:
        entry.update(state="done" if ok else "error", at=time.time())
        if not any(k[0] == platform and e["state"] == "running" for k, e in _IMPORTS.get(uid, {}).items()):
            (CV._RUNNING if platform == "youtube" else IR._RUNNING).discard(uid)


def begin(uid):
    """Start reading every connected account Pit Crew has never read. Safe to call again."""
    started = []
    with _LOCK:
        now, mine = time.time(), _IMPORTS.setdefault(uid, {})
        for platform in PLATFORMS:
            for row in db.connections(uid, platform):
                key = (platform, row["account_id"])
                if not row["account_id"] or key in mine or db.channel_checked(uid, row["account_id"]):
                    continue
                mine[key] = {"platform": platform, "id": row["account_id"], "name": _name(row), "state": "running", "at": now, "seen": False,
                             "personal": platform == "instagram" and not is_professional(row["token"])}
                # The pages under the screen wait for this read rather than starting a second one
                (CV._RUNNING if platform == "youtube" else IR._RUNNING).add(uid)
                started.append((platform, row["account_id"], mine[key]))
    for platform, account, entry in started:
        threading.Thread(target=_run, args=(uid, platform, account, entry), daemon=True).start()


def begin_safely(uid):
    """For the sign-in callbacks: the account is connected by now, so a problem here must not say it isn't. The daily read fills the list."""
    try:
        begin(uid)
    except Exception:  # noqa: BLE001
        traceback.print_exc()


def _status(uid):
    with _LOCK:
        now, mine = time.time(), _IMPORTS.get(uid, {})
        for key in [k for k, e in mine.items() if now - e["at"] > (STUCK if e["state"] == "running" else KEEP)]:
            mine.pop(key)
        shown = [{k: v for k, v in e.items() if k not in ("at", "seen")} for e in mine.values() if not e["seen"]]
    linked = any(db.connections(uid, p) for p in PLATFORMS)
    can = yt.is_configured() or ig.is_configured()
    return {"welcome": can and not linked and not db.onboarded(uid), "imports": shown}


@app.get("/api/import/status")
def first_import_status():
    return jsonify(_status(g.user["id"]))


@app.post("/api/import/begin")
def first_import_begin():
    """The page saw a new connection. (The sign-in's own callback calls begin() too; whichever is first starts the read.)"""
    begin(g.user["id"])
    return jsonify(_status(g.user["id"]))


@app.post("/api/import/seen")
def first_import_seen():
    """The creator is past the screen: don't show it again, for this or for anything still being read."""
    uid = g.user["id"]
    db.set_onboarded(uid)
    with _LOCK:
        for e in _IMPORTS.get(uid, {}).values():
            e["seen"] = True
    return jsonify(ok=True)
