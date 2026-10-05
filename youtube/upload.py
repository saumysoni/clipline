"""
Uploading a Short (and its thumbnail) to YouTube, and plain-English upload errors.
"""
import json
import os
from pathlib import Path


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
            "quotaExceeded": "YouTube's daily upload allowance for Pit Crew is used up. Try again tomorrow.",
            "rateLimitExceeded": "YouTube says Pit Crew is uploading too fast. Wait a few minutes and try again.",
            "uploadLimitExceeded": "Your channel has reached YouTube's upload limit for today. Try again tomorrow.",
            "youtubeSignupRequired": "This Google account has no YouTube channel yet. Create one at youtube.com, "
                                     "or connect the account that owns your channel.",
            "invalidPublishAt": "YouTube didn't accept the scheduled time. Pick a later time and try again.",
            "forbidden": "YouTube didn't allow this upload. Make sure you connected the channel's owner account.",
            "insufficientPermissions": "Pit Crew needs a new YouTube connection for this. Click Connect YouTube, leave "
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
    """Upload one Short and set its thumbnail through the API. On Shorts, that thumbnail shows in search,
    on the home page and in subscriptions; the Shorts feed uses a frame the creator picks in the YouTube app
    (the first frame, see pipeline/cover.py) or, on Partner Program channels, an image set in Studio."""
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
        except Exception as e:  # noqa: BLE001  (never fail an upload over the thumbnail)
            print("Thumbnail upload refused:", repr(e)[:300])
            thumb_note = ("YouTube didn't take the custom thumbnail, usually because the channel isn't phone-verified "
                          "yet: verify it in a minute at youtube.com/verify. Until then, pick the first frame as "
                          "the thumbnail in the YouTube app, or use Download thumbnail and add it in YouTube Studio.")
    return video_id, thumb_note
