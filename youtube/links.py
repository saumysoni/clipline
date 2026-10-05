"""
Recognising links: a YouTube video, a Google Drive file or folder, or something else,
and the plain-English problem with a link pasted in the wrong box.
"""
import re
import urllib.request


# Only the public text (title, description, tags) is read, through YouTube's official API.
# Pit Crew never downloads the video itself from YouTube: YouTube's developer policies forbid it.
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
        "youtube": "That's a YouTube link. Pit Crew can't download videos from YouTube (YouTube's rules don't "
                   "allow it). Upload the original video file or use a Google Drive link instead. To use the "
                   "YouTube link for the title and description, paste it under About this vlog.",
        "youtube_page": "That's a YouTube link. Pit Crew can't download videos from YouTube, so upload the "
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
