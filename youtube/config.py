"""
YouTube/Google settings: the OAuth client (client_secret.json) and the permissions Clipline asks for.
"""
import json

from settings import ROOT


CLIENT_SECRET = ROOT / "client_secret.json"


# "youtube" = manage the channel's videos: upload, see the channel name, change a scheduled time,
# update a title and replace an edited Short (upload the new one, delete the old one).
YOUTUBE_SCOPE = "https://www.googleapis.com/auth/youtube"


SCOPES = [YOUTUBE_SCOPE]


LOGIN_SCOPES = ["openid", "https://www.googleapis.com/auth/userinfo.email",
                "https://www.googleapis.com/auth/userinfo.profile"]


NET_TIMEOUT = 15  # seconds; a slow network must never freeze the page


def is_configured():
    return CLIENT_SECRET.exists()


def client_id():
    info = json.loads(CLIENT_SECRET.read_text(encoding="utf-8"))
    return (info.get("web") or info.get("installed") or {}).get("client_id", "")
