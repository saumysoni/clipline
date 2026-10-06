"""
Uploading a whole vlog (not a Short) with its title, description (with chapters), tags, thumbnail and
visibility: public now, scheduled, unlisted or private. Raises like upload_short (see upload_error_message).
"""
import os
from pathlib import Path

PRIVACY = ("public", "unlisted", "private")


def upload_vlog(youtube, video_path, title, description, tags, privacy="public", publish_at=None,
                thumb_path=None, progress=lambda pct: None):
    """Returns (video_id, thumb_note). publish_at (aware datetime) schedules it: private until then."""
    from googleapiclient.http import MediaFileUpload

    status = {"selfDeclaredMadeForKids": False}
    if publish_at:
        status.update(privacyStatus="private", publishAt=publish_at.isoformat(timespec="seconds"))
    else:
        status["privacyStatus"] = privacy if privacy in PRIVACY else "public"
    body = {"snippet": {"title": title[:100], "description": description[:5000], "tags": tags,
                        "categoryId": os.getenv("YOUTUBE_VLOG_CATEGORY_ID", os.getenv("YOUTUBE_CATEGORY_ID", "22"))},
            "status": status}
    ext = Path(video_path).suffix.lower()
    mime = {".mov": "video/quicktime", ".webm": "video/webm", ".mkv": "video/x-matroska"}.get(ext, "video/mp4")
    media = MediaFileUpload(str(video_path), mimetype=mime, chunksize=16 * 1024 * 1024, resumable=True)
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        st, resp = req.next_chunk()
        if st:
            progress(st.progress() * 100)
    video_id = resp["id"]
    note = None
    if thumb_path and Path(thumb_path).exists():
        try:
            youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(thumb_path))).execute()
        except Exception as e:  # noqa: BLE001  (never fail an upload over the thumbnail)
            print("Thumbnail upload refused:", repr(e)[:300])
            note = ("YouTube didn't take the custom thumbnail, usually because the channel isn't phone-verified yet "
                    "(youtube.com/verify takes a minute). Add it in YouTube Studio: Download thumbnail, then Studio › Edit.")
    return video_id, note
