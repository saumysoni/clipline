"""
Uploads finished Shorts to the creator's YouTube channel and schedules them.

Needs client_secret.json (a free OAuth "Desktop app" client from Google Cloud, see README).
The first upload opens a Google sign-in page; the creator approves once and the
permission is saved to token.json.
"""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CLIENT_SECRET = ROOT / "client_secret.json"
TOKEN = ROOT / "token.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def is_configured():
    return CLIENT_SECRET.exists()


def get_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None
        if not creds or not creds.valid:
            if not CLIENT_SECRET.exists():
                raise RuntimeError("client_secret.json is missing. See README, step 5.")
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
            creds = flow.run_local_server(port=0, prompt="consent")
        TOKEN.write_text(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def plan_times(n, mode, first_day=None):
    """Return a list of local datetimes (or None for 'post now')."""
    tz = datetime.now().astimezone().tzinfo
    day = first_day or (datetime.now(tz) + timedelta(days=1)).date()
    times = []
    for k in range(n):
        if mode == "now":
            times.append(None)
        elif mode == "two":
            d = day + timedelta(days=k // 2)
            times.append(datetime(d.year, d.month, d.day, 18 if k % 2 else 12, 0, tzinfo=tz))
        else:
            d = day + timedelta(days=k)
            hour = 12 if mode == "d12" else 18
            times.append(datetime(d.year, d.month, d.day, hour, 0, tzinfo=tz))
    return times


def upload_short(youtube, video_path, title, description, tags, publish_at=None,
                 thumb_path=None, progress=lambda pct: None):
    from googleapiclient.http import MediaFileUpload

    status = {"selfDeclaredMadeForKids": False}
    if publish_at:
        # YouTube only accepts a scheduled time on private videos; it flips them public at that time.
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at.astimezone().isoformat(timespec="seconds")
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
            thumb_note = "Thumbnail not set automatically; add it in YouTube Studio. (" + str(e)[:120] + ")"
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


def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Clipline"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_video_info(url):
    """Title, description and tags of a public (or unlisted) YouTube video.

    Uses the YouTube Data API when YOUTUBE_API_KEY is set (free key from Google Cloud);
    otherwise YouTube's public oEmbed lookup, which only gives the title.
    """
    vid = video_id_from_url(url)
    if not vid:
        raise RuntimeError("That doesn't look like a YouTube video link.")
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
