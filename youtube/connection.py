"""
Each creator's saved YouTube connection: loading it, refreshing it, the channel name, signing out.
"""
import json
import urllib.request

from accounts import db

from youtube.config import NET_TIMEOUT, SCOPES, is_configured


# One per Clipline user, in the database. Keep every read and write of it in these three functions.
_CHANNEL = {}  # user id -> their channel, looked up once per connection


def _read_token(user_id):
    return db.youtube_token(user_id)


def _save_token(user_id, creds):
    db.save_youtube_token(user_id, creds.to_json())


def _drop_token(user_id):
    db.drop_youtube_token(user_id)
    _CHANNEL.pop(user_id, None)


def _quick_request():
    from google.auth.transport.requests import Request

    class QuickRequest(Request):
        def __call__(self, *a, timeout=NET_TIMEOUT, **kw):
            return super().__call__(*a, timeout=timeout, **kw)
    return QuickRequest()


def load_creds(user_id):
    """This user's YouTube connection, refreshed if needed, or None when they haven't connected.

    A connection saved before Clipline asked for every scope in SCOPES counts as not connected, so the
    creator connects once more. Network trouble raises OSError instead, so being offline doesn't
    disconnect anyone."""
    from google.auth.exceptions import RefreshError, TransportError
    from google.oauth2.credentials import Credentials

    info = _read_token(user_id)
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
                _drop_token(user_id)
                return None
            raise OSError("Google couldn't refresh the sign-in right now") from e  # e.g. Google is busy
        _save_token(user_id, creds)
    return creds


def _lookup_channel(access_token):
    q = urllib.parse.urlencode({"part": "snippet", "mine": "true"})
    req = urllib.request.Request(f"https://www.googleapis.com/youtube/v3/channels?{q}",
                                 headers={"Authorization": f"Bearer {access_token}", "User-Agent": "Clipline"})
    with urllib.request.urlopen(req, timeout=NET_TIMEOUT) as r:
        items = json.loads(r.read().decode("utf-8")).get("items") or []
    if not items:
        return None
    sn = items[0]["snippet"]
    handle = sn.get("customUrl", "")
    return {"id": items[0]["id"], "title": sn.get("title", ""), "handle": handle if handle.startswith("@") or not handle
            else "@" + handle, "thumb": ((sn.get("thumbnails") or {}).get("default") or {}).get("url", "")}


def access_token(user_id):
    """A fresh access token for this user's YouTube connection, or None if not connected or offline."""
    try:
        creds = load_creds(user_id)
    except OSError:
        return None
    return creds.token if creds else None


def account(user_id):
    """What the page shows about this user's YouTube: {"configured", "signed_in", "channel", "offline"}."""
    out = {"configured": is_configured(), "signed_in": False, "channel": None, "offline": False}
    try:
        creds = load_creds(user_id)
        if not creds:
            return out
        out["signed_in"] = True
        if user_id not in _CHANNEL:
            channel = _lookup_channel(creds.token)
            if channel:
                _CHANNEL[user_id] = channel
        out["channel"] = _CHANNEL.get(user_id)
    except (OSError, ValueError) as e:  # offline, or Google is slow: still connected, name unknown for now
        print("Couldn't check the YouTube connection:", repr(e))
        out["signed_in"] = bool(_read_token(user_id))
        out["offline"] = True
    return out


def sign_out(user_id):
    """Disconnect this user's YouTube here and ask Google to revoke it (also if that request fails)."""
    info = _read_token(user_id) or {}
    tok = info.get("refresh_token") or info.get("token")
    if tok:
        try:
            req = urllib.request.Request("https://oauth2.googleapis.com/revoke",
                                         data=urllib.parse.urlencode({"token": tok}).encode(),
                                         headers={"Content-Type": "application/x-www-form-urlencoded"})
            urllib.request.urlopen(req, timeout=NET_TIMEOUT).close()
        except (OSError, urllib.error.HTTPError) as e:
            print("Couldn't revoke the YouTube connection at Google (it's forgotten here anyway):", repr(e))
    _drop_token(user_id)


def get_service(user_id):
    from googleapiclient.discovery import build

    try:
        creds = load_creds(user_id)
    except OSError as e:
        raise RuntimeError("Couldn't reach YouTube. Check your internet connection and try again.") from e
    if not creds:
        raise RuntimeError("Your YouTube channel isn't connected. Click Connect YouTube, then try again.")
    return build("youtube", "v3", credentials=creds, cache_discovery=False)
