"""
YouTube/Google settings: the OAuth client and the permissions Pit Crew asks for.

The OAuth client comes from (first found wins):
  1. GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET in .env / the server's environment (use this in the cloud)
  2. client_secret.json in the app's folder
  3. Google's own download name, client_secret_<numbers>.apps.googleusercontent.com.json, in the app's folder
"""
import json
import os

from settings import ROOT


CLIENT_SECRET = ROOT / "client_secret.json"


# "youtube" = manage the channel's videos: upload, see the channel name, change a scheduled time,
# update a title and replace an edited Short (upload the new one, delete the old one).
YOUTUBE_SCOPE = "https://www.googleapis.com/auth/youtube"


SCOPES = [YOUTUBE_SCOPE]  # what a connection must have (posting, scheduling, editing)


# Read-only analytics (watch time, retention, traffic sources, audience). Asked for when connecting, but
# optional: a connection without it still posts, and the Analytics page asks to reconnect for the rest.
ANALYTICS_SCOPE = "https://www.googleapis.com/auth/yt-analytics.readonly"
CONNECT_SCOPES = SCOPES + [ANALYTICS_SCOPE]


LOGIN_SCOPES = ["openid", "https://www.googleapis.com/auth/userinfo.email",
                "https://www.googleapis.com/auth/userinfo.profile"]


NET_TIMEOUT = 15  # seconds; a slow network must never freeze the page


def _secret_file():
    if CLIENT_SECRET.exists():
        return CLIENT_SECRET
    found = sorted(ROOT.glob("client_secret*.json"))
    return found[0] if found else None


def client_config():
    """The OAuth client as the dict google_auth_oauthlib wants, or None if it isn't set up."""
    cid, secret = os.getenv("GOOGLE_CLIENT_ID", "").strip(), os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    if cid and secret:
        return {"web": {"client_id": cid, "client_secret": secret,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token"}}
    f = _secret_file()
    if not f:
        return None
    try:
        info = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print(f"{f.name} isn't a valid Google client file; download it again from Google Cloud.")
        return None
    return info if (info.get("web") or info.get("installed")) else None


def is_configured():
    return client_config() is not None


def client_id():
    info = client_config() or {}
    return (info.get("web") or info.get("installed") or {}).get("client_id", "")
