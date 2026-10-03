"""
Google sign-in for Clipline accounts, each creator's YouTube connection, and uploading/scheduling Shorts.

Needs client_secret.json (a free OAuth "Web application" client from Google Cloud, see README step 5).
Two kinds of Google sign-in share one callback (/api/youtube/callback):
- "login": Sign in with Google to Clipline. Asks only for name and email (no warning screen, no user cap).
- "youtube": Connect YouTube. Asks to manage the creator's videos; saved per user in the database.
The waiting sign-in (state, PKCE verifier) lives in the creator's own session cookie, so the callback only
ever finishes a sign-in that the same browser started, and any server process can finish it.
"""
import json
import os
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import db

ROOT = Path(__file__).resolve().parent
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


# --------------------------------------------------------------------------- saved YouTube connection
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


# --------------------------------------------------------------------------- Google sign-in (both kinds)
def _allow_http(redirect_uri):
    # oauthlib refuses plain http; that's fine (and needed) only for this computer's own address.
    host = urllib.parse.urlparse(redirect_uri).hostname or ""
    if host in ("localhost", "127.0.0.1", "::1"):
        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    # Google may grant more or fewer scopes than asked; Clipline checks them itself.
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"


def start_google(purpose, redirect_uri, next_id="", popup=False):
    """(Google's sign-in address, the waiting sign-in to keep in the creator's session).
    purpose is "login" (Clipline account) or "youtube" (connect a channel)."""
    from google_auth_oauthlib.flow import Flow

    if not CLIENT_SECRET.exists():
        raise RuntimeError("Google sign-in isn't set up yet: client_secret.json is missing. "
                           "Follow README step 5, then try again.")
    _allow_http(redirect_uri)
    scopes = LOGIN_SCOPES if purpose == "login" else SCOPES
    flow = Flow.from_client_secrets_file(str(CLIENT_SECRET), scopes, redirect_uri=redirect_uri)
    extra = ({"prompt": "select_account"} if purpose == "login"
             else {"access_type": "offline", "prompt": "consent select_account"})
    url, state = flow.authorization_url(**extra)
    return url, {"state": state, "verifier": flow.code_verifier, "redirect_uri": redirect_uri,
                 "purpose": purpose, "next": next_id, "popup": popup}


def _exchange(args, pending, scopes):
    """Swap Google's one-time code for tokens. Raises RuntimeError in plain words."""
    from google_auth_oauthlib.flow import Flow

    if args.get("error"):
        if args["error"] == "access_denied":
            raise RuntimeError("Sign-in was cancelled. Try again when you're ready.")
        raise RuntimeError(f"Google didn't finish the sign-in ({args['error']}). Try again.")
    if not pending or not args.get("code") or not secrets.compare_digest(
            str(args.get("state", "")), str(pending.get("state", ""))):
        raise RuntimeError("This sign-in page is out of date. Close it and try again.")
    _allow_http(pending["redirect_uri"])
    flow = Flow.from_client_secrets_file(str(CLIENT_SECRET), scopes, redirect_uri=pending["redirect_uri"],
                                         code_verifier=pending["verifier"], autogenerate_code_verifier=False)
    try:
        token = flow.fetch_token(code=args["code"], timeout=NET_TIMEOUT)
    except Exception as e:
        print("Google sign-in failed:", repr(e))
        raise RuntimeError("Google didn't accept the sign-in. Try again.") from e
    return flow, token


def finish_login(args, pending):
    """Google's reply to Sign in with Google -> {"sub", "email", "email_verified", "name"}."""
    from google.oauth2 import id_token

    _, token = _exchange(args, pending, LOGIN_SCOPES)
    try:
        info = id_token.verify_oauth2_token(token.get("id_token"), _quick_request(), client_id(),
                                              clock_skew_in_seconds=10)  # computer clocks drift a little
    except Exception as e:
        print("Google ID token check failed:", repr(e))
        raise RuntimeError("Google's sign-in reply couldn't be checked. Try again.") from e
    if not info.get("email"):
        raise RuntimeError("Google didn't share an email address for this account, so Clipline can't sign you in.")
    return {"sub": info["sub"], "email": info["email"].lower(), "email_verified": bool(info.get("email_verified")),
            "name": info.get("name", "")}


def finish_youtube(args, pending, user_id):
    """Google's reply to Connect YouTube: save the connection for this user and return their channel
    ({"id", "title", "thumb"}). Raises RuntimeError with a plain message."""
    flow, token = _exchange(args, pending, SCOPES)
    granted = token.get("scope") or []
    granted = set(granted.split() if isinstance(granted, str) else granted)
    if YOUTUBE_SCOPE not in granted:
        raise RuntimeError("Clipline needs permission to manage your YouTube videos, so it can upload, schedule "
                           "and update your Shorts. Connect again and leave that box ticked.")
    creds = flow.credentials
    if not creds.refresh_token:
        raise RuntimeError("Google didn't give Clipline a lasting connection. Open "
                           "https://myaccount.google.com/permissions, remove Clipline, then connect again.")
    try:
        channel = _lookup_channel(creds.token)
    except urllib.error.HTTPError as e:
        print("YouTube channel lookup failed:", e.code, e.read()[:300])
        raise RuntimeError("YouTube didn't answer Clipline. In Google Cloud, check that YouTube Data API v3 is "
                           "enabled for this project (README step 5.2), then connect again.") from e
    except OSError as e:
        raise RuntimeError("Couldn't reach YouTube. Check your internet connection and connect again.") from e
    if not channel:
        raise RuntimeError("This Google account has no YouTube channel. Create one at youtube.com, or connect "
                           "with the account that owns your channel.")
    _save_token(user_id, creds)
    _CHANNEL[user_id] = channel
    return channel


def _lookup_channel(access_token):
    q = urllib.parse.urlencode({"part": "snippet", "mine": "true"})
    req = urllib.request.Request(f"https://www.googleapis.com/youtube/v3/channels?{q}",
                                 headers={"Authorization": f"Bearer {access_token}", "User-Agent": "Clipline"})
    with urllib.request.urlopen(req, timeout=NET_TIMEOUT) as r:
        items = json.loads(r.read().decode("utf-8")).get("items") or []
    if not items:
        return None
    sn = items[0]["snippet"]
    return {"id": items[0]["id"], "title": sn.get("title", ""),
            "thumb": ((sn.get("thumbnails") or {}).get("default") or {}).get("url", "")}


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


# --------------------------------------------------------------------------- when each Short goes out
SPACINGS = (6, 12, 24, 48, 72, 168)  # hours between Shorts that the custom schedule offers
MIN_LEAD = timedelta(minutes=15)  # a scheduled time closer than this may already be past by upload time


def zone(name):
    """The creator's time zone (the browser sends its name), or this computer's zone."""
    try:
        return ZoneInfo(name) if name else datetime.now().astimezone().tzinfo
    except (ZoneInfoNotFoundError, ValueError):
        return datetime.now().astimezone().tzinfo


def plan_times(n, mode, tz_name=None, start=None, every_hours=24):
    """Return n aware datetimes in the creator's time zone (or None for 'post now').

    Presets start tomorrow; "custom" starts at `start` ("YYYY-MM-DDTHH:MM", the creator's local time)
    and adds `every_hours` for each next Short. Raises RuntimeError if a custom time isn't usable."""
    tz = zone(tz_name)
    if mode == "now":
        return [None] * n
    if mode == "custom":
        try:
            first = datetime.fromisoformat(start or "").replace(tzinfo=tz)
        except ValueError:
            raise RuntimeError("Pick the date and time for the first Short.") from None
        if first < datetime.now(tz) + MIN_LEAD:
            raise RuntimeError("Pick a time at least 15 minutes from now.")
        if every_hours not in SPACINGS:
            every_hours = 24
        return [first + timedelta(hours=every_hours * k) for k in range(n)]
    day = (datetime.now(tz) + timedelta(days=1)).date()
    times = []
    for k in range(n):
        if mode == "two":
            d = day + timedelta(days=k // 2)
            times.append(datetime(d.year, d.month, d.day, 18 if k % 2 else 12, 0, tzinfo=tz))
        else:
            d = day + timedelta(days=k)
            hour = 12 if mode == "d12" else 18
            times.append(datetime(d.year, d.month, d.day, hour, 0, tzinfo=tz))
    return times


def video_states(youtube, ids):
    """Live state of uploaded videos: {id: {"privacy", "publish_at", "title"}}. Missing ids were deleted."""
    out = {}
    ids = [i for i in ids if i]
    for k in range(0, len(ids), 50):
        resp = youtube.videos().list(part="status,snippet", id=",".join(ids[k:k + 50])).execute()
        for it in resp.get("items", []):
            st = it.get("status", {})
            out[it["id"]] = {"privacy": st.get("privacyStatus"), "publish_at": st.get("publishAt"),
                             "title": it.get("snippet", {}).get("title", "")}
    return out


def is_live(state):
    """True once people can see the video (public, or unlisted)."""
    return bool(state) and state.get("privacy") in ("public", "unlisted")


# status fields YouTube lets an app write back (anything else in the reply is read-only)
_STATUS_WRITABLE = ("privacyStatus", "publishAt", "embeddable", "license", "publicStatsViewable",
                    "selfDeclaredMadeForKids", "containsSyntheticMedia")


def reschedule(youtube, video_id, when):
    """Move a scheduled (private) Short to a new time. Raises RuntimeError in plain words."""
    items = youtube.videos().list(part="status", id=video_id).execute().get("items", [])
    if not items:
        raise RuntimeError("This Short isn't on YouTube any more (was it deleted in YouTube Studio?).")
    st = items[0]["status"]
    if st.get("privacyStatus") != "private":
        raise RuntimeError("This Short is already public, so it can't be scheduled again. "
                           "Change it in YouTube Studio if you need to.")
    body = {k: st[k] for k in _STATUS_WRITABLE if k in st}
    body.update(privacyStatus="private", publishAt=when.isoformat(timespec="seconds"))
    youtube.videos().update(part="status", body={"id": video_id, "status": body}).execute()


def update_title(youtube, video_id, title):
    """Change only the title of an uploaded Short (description, tags and category are kept)."""
    items = youtube.videos().list(part="snippet", id=video_id).execute().get("items", [])
    if not items:
        raise RuntimeError("This Short isn't on YouTube any more (was it deleted in YouTube Studio?).")
    sn = items[0]["snippet"]
    body = {"title": title[:100], "categoryId": sn.get("categoryId", "22"),
            "description": sn.get("description", ""), "tags": sn.get("tags", [])}
    youtube.videos().update(part="snippet", body={"id": video_id, "snippet": body}).execute()


def delete_video(youtube, video_id):
    youtube.videos().delete(id=video_id).execute()


def upload_error_message(e):
    """A plain sentence for anything that stops an upload."""
    from google.auth.exceptions import RefreshError
    from googleapiclient.errors import HttpError

    if isinstance(e, RuntimeError):
        return str(e)
    if isinstance(e, RefreshError):
        return "Your YouTube connection has expired. Click Connect YouTube, then press the button again."
    if isinstance(e, HttpError):
        reason = ""
        try:
            reason = json.loads(e.content.decode("utf-8"))["error"]["errors"][0].get("reason", "")
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            pass
        msgs = {
            "quotaExceeded": "YouTube's daily upload allowance for Clipline is used up. Try again tomorrow.",
            "rateLimitExceeded": "YouTube says Clipline is uploading too fast. Wait a few minutes and try again.",
            "uploadLimitExceeded": "Your channel has reached YouTube's upload limit for today. Try again tomorrow.",
            "youtubeSignupRequired": "This Google account has no YouTube channel yet. Create one at youtube.com, "
                                     "or connect the account that owns your channel.",
            "invalidPublishAt": "YouTube didn't accept the scheduled time. Pick a later time and try again.",
            "forbidden": "YouTube didn't allow this upload. Make sure you connected the channel's owner account.",
            "insufficientPermissions": "Clipline needs a new YouTube connection for this. Click Connect YouTube, leave "
                                       "every box ticked, then try again.",
        }
        if reason in msgs:
            return msgs[reason]
        if e.resp.status == 401:
            return "Your YouTube connection has expired. Click Connect YouTube, then press the button again."
        return f"YouTube refused the upload ({reason or e.resp.status}). Try again in a few minutes."
    if isinstance(e, OSError):
        return "Couldn't reach YouTube. Check your internet connection and try again."
    return "Something went wrong while posting. Try again; Shorts that already went up won't be posted twice."


def upload_short(youtube, video_path, title, description, tags, publish_at=None,
                 thumb_path=None, progress=lambda pct: None):
    from googleapiclient.http import MediaFileUpload

    status = {"selfDeclaredMadeForKids": False}
    if publish_at:
        # YouTube only accepts a scheduled time on private videos; it flips them public at that time.
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at.isoformat(timespec="seconds")
    else:
        status["privacyStatus"] = os.getenv("POST_NOW_PRIVACY", "public")

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:4900],
            "tags": tags[:15],
            "categoryId": os.getenv("YOUTUBE_CATEGORY_ID", "22"),
        },
        "status": status,
    }
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        st, resp = req.next_chunk()
        if st:
            progress(st.progress() * 100)
    video_id = resp["id"]

    thumb_note = None
    if thumb_path and Path(thumb_path).exists():
        try:
            youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(thumb_path))).execute()
        except Exception as e:  # custom Shorts thumbnails are not available on every channel yet
            print("Thumbnail upload refused:", repr(e)[:300])
            thumb_note = (f"YouTube didn't accept the custom thumbnail (it needs a phone-verified channel with custom "
                          f"thumbnails turned on). Add it in YouTube Studio; the file is {Path(thumb_path).name} "
                          f"in this job's folder.")
    return video_id, thumb_note


# --------------------------------------------------------------------------- reading a vlog's info
# Only the public text (title, description, tags) is read, through YouTube's official API.
# Clipline never downloads the video itself from YouTube: YouTube's developer policies forbid it.
VIDEO_ID_RE = re.compile(r"(?:v=|youtu\.be/|/shorts/|/live/|/embed/|/v/)([A-Za-z0-9_-]{11})")


def video_id_from_url(url):
    url = (url or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url):
        return url
    m = VIDEO_ID_RE.search(url)
    return m.group(1) if m else None


def link_kind(url):
    """What a pasted link points to: youtube, youtube_page (channel, playlist...), drive_file,
    drive_folder, drive_page, other, or "" when empty. Used to catch links pasted in the wrong box."""
    url = (url or "").strip()
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url if "://" in url else "https://" + url)
    host = (parsed.hostname or "").lower()
    if host == "youtu.be" or host.endswith(("youtube.com", "youtube-nocookie.com")):
        return "youtube" if video_id_from_url(url) else "youtube_page"
    if host in ("drive.google.com", "docs.google.com"):
        if "/folders/" in parsed.path:
            return "drive_folder"
        if "/file/d/" in parsed.path or "id" in urllib.parse.parse_qs(parsed.query):
            return "drive_file"
        return "drive_page"
    return "other"


def video_link_problem(url):
    """Plain-English problem with a link pasted as the vlog's video (a Google Drive link), or None."""
    return {
        "youtube": "That's a YouTube link. Clipline can't download videos from YouTube (YouTube's rules don't "
                   "allow it). Upload the original video file or use a Google Drive link instead. To use the "
                   "YouTube link for the title and description, paste it under About this vlog.",
        "youtube_page": "That's a YouTube link. Clipline can't download videos from YouTube, so upload the "
                        "original video file or use a Google Drive link instead.",
        "drive_folder": "That's a link to a Drive folder. Open the folder, right-click the video, choose "
                        "Share, then Copy link, and paste that link instead.",
        "drive_page": "That's a link to a Drive page, not to one video. In Drive, right-click the video, "
                      "choose Share, then Copy link, and paste that link instead.",
        "other": "That doesn't look like a Google Drive link. Paste a link that starts with "
                 "https://drive.google.com, or upload the video file instead.",
    }.get(link_kind(url))


def youtube_link_problem(url):
    """Plain-English problem with a link pasted as the vlog's YouTube link, or None."""
    return {
        "drive_file": "That's a Google Drive link. Paste it in the Google Drive box under Your vlog; "
                      "this box is for the vlog's YouTube link.",
        "drive_folder": "That's a Google Drive link. This box is for the vlog's YouTube link.",
        "drive_page": "That's a Google Drive link. This box is for the vlog's YouTube link.",
        "youtube_page": "That's a YouTube link, but not to one video (maybe a channel or playlist). "
                        "Open the vlog on YouTube and copy its link from the Share button.",
        "other": "That doesn't look like a YouTube video link. Open the vlog on YouTube and copy its link "
                 "from the Share button.",
    }.get(link_kind(url))


def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Clipline"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_video_info(url):
    """Title, description and tags of a public (or unlisted) YouTube video.

    Uses the YouTube Data API when YOUTUBE_API_KEY is set (free key from Google Cloud);
    otherwise YouTube's public oEmbed lookup, which only gives the title.
    """
    problem = youtube_link_problem(url)
    vid = video_id_from_url(url)
    if problem or not vid:
        raise RuntimeError(problem or "That doesn't look like a YouTube video link.")
    key = os.getenv("YOUTUBE_API_KEY")
    if key:
        q = urllib.parse.urlencode({"part": "snippet", "id": vid, "key": key})
        try:
            data = _get_json(f"https://www.googleapis.com/youtube/v3/videos?{q}")
        except urllib.error.HTTPError as e:
            raise RuntimeError("YouTube refused the request. Check YOUTUBE_API_KEY in .env "
                               f"(and that the YouTube Data API is enabled for it). ({e.code})") from e
        except OSError as e:
            raise RuntimeError("Couldn't reach YouTube. Check your internet connection.") from e
        items = data.get("items") or []
        if not items:
            raise RuntimeError("YouTube couldn't find that video. Is it public or unlisted, not private?")
        sn = items[0]["snippet"]
        return {"video_id": vid, "title": sn.get("title", ""), "description": sn.get("description", ""),
                "tags": sn.get("tags", [])[:30], "channel": sn.get("channelTitle", ""), "complete": True}
    q = urllib.parse.urlencode({"url": f"https://www.youtube.com/watch?v={vid}", "format": "json"})
    try:
        data = _get_json(f"https://www.youtube.com/oembed?{q}")
    except urllib.error.HTTPError as e:
        raise RuntimeError("YouTube couldn't find that video. Is it public or unlisted, not private?") from e
    except OSError as e:
        raise RuntimeError("Couldn't reach YouTube. Check your internet connection.") from e
    return {"video_id": vid, "title": data.get("title", ""), "description": "", "tags": [],
            "channel": data.get("author_name", ""), "complete": False}
