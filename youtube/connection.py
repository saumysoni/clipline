"""
Each creator's saved YouTube connections: several channels per creator, one active (where new Shorts go).
Loading and refreshing a channel's sign-in, the channel list, switching, disconnecting.

Every function takes channel=None (the active channel) or a YouTube channel id. Anything that acts on a Short
already on YouTube must pass the channel it went up on (its upload record's "channel"), never the active one.
"""
import json
import urllib.request

from accounts import db

from youtube.config import NET_TIMEOUT, SCOPES, is_configured


NOT_CONNECTED = ("This Short is on a YouTube channel that isn't connected to Pit Crew any more. Add that channel "
                 "again (Channels › Add channel), then try again.")


def _row(user_id, channel=None):
    return db.connection(user_id, "youtube", channel)


def save_connection(user_id, creds, channel):
    """A channel the creator just connected: add it (or update it) and make it the active one."""
    db.save_connection(user_id, "youtube", channel["id"], creds.to_json(), channel)


def _quick_request():
    from google.auth.transport.requests import Request

    class QuickRequest(Request):
        def __call__(self, *a, timeout=NET_TIMEOUT, **kw):
            return super().__call__(*a, timeout=timeout, **kw)
    return QuickRequest()


def load_creds(user_id, channel=None, row=None):
    """A channel's YouTube sign-in (channel None: the active one), refreshed if needed, or None when it isn't
    connected.

    A connection saved before Pit Crew asked for every scope in SCOPES counts as not connected, so the
    creator connects once more. Network trouble raises OSError instead, so being offline doesn't
    disconnect anyone."""
    from google.auth.exceptions import RefreshError, TransportError
    from google.oauth2.credentials import Credentials

    row = row or _row(user_id, channel)
    info = (row or {}).get("token")
    if not info or not set(SCOPES) <= set(info.get("scopes") or []):
        return None
    try:
        creds = Credentials.from_authorized_user_info(info)
    except ValueError:
        return None
    if not creds.valid:
        if not creds.refresh_token:
            return None
        try:
            creds.refresh(_quick_request())
        except TransportError as e:
            raise OSError("Couldn't reach Google") from e
        except RefreshError as e:
            if "invalid_grant" in str(e):  # revoked in the Google account, or expired: connect again
                db.drop_connection(row["id"])
                return None
            raise OSError("Google couldn't refresh the sign-in right now") from e  # e.g. Google is busy
        db.update_connection(row["id"], token=creds.to_json())
    return creds


def _lookup_channel(access_token):
    q = urllib.parse.urlencode({"part": "snippet", "mine": "true"})
    req = urllib.request.Request(f"https://www.googleapis.com/youtube/v3/channels?{q}",
                                 headers={"Authorization": f"Bearer {access_token}", "User-Agent": "PitCrew"})
    with urllib.request.urlopen(req, timeout=NET_TIMEOUT) as r:
        items = json.loads(r.read().decode("utf-8")).get("items") or []
    if not items:
        return None
    sn = items[0]["snippet"]
    handle = sn.get("customUrl", "")
    return {"id": items[0]["id"], "title": sn.get("title", ""), "handle": handle if handle.startswith("@") or not handle
            else "@" + handle, "thumb": ((sn.get("thumbnails") or {}).get("default") or {}).get("url", "")}


def access_token(user_id, channel=None):
    """A fresh access token for a YouTube connection, or None if not connected or offline."""
    try:
        creds = load_creds(user_id, channel)
    except OSError:
        return None
    return creds.token if creds else None


def _fill_channel(user_id):
    """Connections moved from the old one-per-user table don't know their channel yet: look it up once."""
    for row in db.connections(user_id, "youtube"):
        if row["account_id"]:
            continue
        try:
            creds = load_creds(user_id, row=row)
            channel = creds and _lookup_channel(creds.token)
        except (OSError, ValueError) as e:
            print("Couldn't look up a YouTube channel:", repr(e))
            continue
        if channel:
            db.set_account_id(row["id"], channel["id"], channel)


def account(user_id):
    """What the page shows: {"configured", "signed_in", "channel" (the active one), "channels" (every connected
    channel, each with "active"), "offline"}."""
    out = {"configured": is_configured(), "signed_in": False, "channel": None, "channels": [], "offline": False}
    _fill_channel(user_id)
    rows = db.connections(user_id, "youtube")
    out["channels"] = [{**(r["profile"] or {"id": r["account_id"], "title": "", "handle": "", "thumb": ""}),
                        "active": r["active"]} for r in rows if r["account_id"]]
    try:
        creds = load_creds(user_id)
        if not creds:
            return out
        out["signed_in"] = True
        active = _row(user_id)
        out["channel"] = active["profile"] if active else None
    except (OSError, ValueError) as e:  # offline, or Google is slow: still connected, checked again next time
        print("Couldn't check the YouTube connection:", repr(e))
        active = _row(user_id)
        out["signed_in"] = bool(active)
        out["channel"] = active["profile"] if active else None
        out["offline"] = True
    return out


def switch(user_id, channel):
    """Make a connected channel the active one. False if it isn't connected."""
    return db.set_active(user_id, "youtube", channel)


def sign_out(user_id, channel=None):
    """Disconnect a channel (None: the active one) and ask Google to revoke it (also if that request fails)."""
    row = _row(user_id, channel)
    if not row:
        return
    info = row["token"] or {}
    tok = info.get("refresh_token") or info.get("token")
    if tok:
        try:
            req = urllib.request.Request("https://oauth2.googleapis.com/revoke",
                                         data=urllib.parse.urlencode({"token": tok}).encode(),
                                         headers={"Content-Type": "application/x-www-form-urlencoded"})
            urllib.request.urlopen(req, timeout=NET_TIMEOUT).close()
        except (OSError, urllib.error.HTTPError) as e:
            print("Couldn't revoke the YouTube connection at Google (it's forgotten here anyway):", repr(e))
    db.drop_connection(row["id"])


def get_service(user_id, channel=None):
    """The YouTube Data API for a channel (None: the active one). Raises RuntimeError in plain words."""
    from googleapiclient.discovery import build

    try:
        creds = load_creds(user_id, channel)
    except OSError as e:
        raise RuntimeError("Couldn't reach YouTube. Check your internet connection and try again.") from e
    if not creds:
        raise RuntimeError(NOT_CONNECTED if channel
                           else "Your YouTube channel isn't connected. Click Connect YouTube, then try again.")
    return build("youtube", "v3", credentials=creds, cache_discovery=False)
