"""
Posting a Reel: make a container, send the video bytes (resumable upload, so no public video address is
needed), wait until Instagram has processed it, publish, and read back the Reel's link.
Instagram has no scheduling for apps: Pit Crew's own scheduler (web/instagram_posting.py) calls post_reel
at the chosen time.
"""
import time

from instagram.config import API_VERSION, GRAPH
from instagram.connection import is_professional, load
from instagram.http import InstagramError, call

PROCESS_WAIT = 15 * 60  # Instagram usually needs 30 s – 3 min to process a Reel
MAX_BYTES = 100 * 1024 * 1024


def caption_for(it, vlog, ig_handle=""):
    """The Reel caption: hook (or title), where the full video is, the YouTube channel, hashtags.
    Links in captions can't be tapped on Instagram, so the full video is named rather than linked."""
    lead = it.get("hook", "") if it.get("hook_mode", "text") != "none" else ""
    parts = [it.get("title", "").strip()]
    if lead and lead.strip().lower() != parts[0].lower():
        parts.append(lead.strip())
    vlog = vlog or {}
    # A YouTube @handle would tag whoever owns that name on Instagram, so it's written as the channel's address.
    handle = vlog.get("channel_handle") or ""
    where = f"youtube.com/{handle}" if handle.startswith("@") else vlog.get("channel") or ""
    if vlog.get("title"):
        parts.append(f"Full video on YouTube: \u201c{vlog['title']}\u201d" + (f" ({where})" if where else ""))
    elif where:
        parts.append(f"Full video on YouTube: {where}")
    tags = [t for t in it.get("hashtags", []) if t] + ["reels"]
    parts.append(" ".join("#" + t for t in tags[:28]))  # Instagram allows 30 hashtags
    return "\n\n".join(p for p in parts if p)[:2200]


def post_reel(user_id, video_path, caption, cover_ms=100, progress=None):
    """Publish the video as a Reel now. Returns {"media_id", "permalink"}. Raises InstagramError."""
    say = progress or (lambda *_: None)
    info = load(user_id)
    if not info:
        raise InstagramError("Connect Instagram first.", expired=True)
    if not is_professional(info):
        raise InstagramError("Instagram only lets apps post to Business or Creator accounts. Switch your account "
                             "to professional in the Instagram app, then connect again.")
    size = video_path.stat().st_size
    if size > MAX_BYTES:
        raise InstagramError("This Short is bigger than Instagram's 100 MB limit for Reels posted by apps.")
    tok, base = info["token"], f"{GRAPH}/{API_VERSION}"
    say("Preparing the Reel")
    made = call("POST", f"{base}/{info['ig_id']}/media",
                data={"media_type": "REELS", "upload_type": "resumable", "caption": caption,
                      "share_to_feed": "true", "thumb_offset": str(cover_ms), "access_token": tok})
    container = made["id"]
    say("Uploading the video")
    call("POST", made.get("uri") or f"https://rupload.facebook.com/ig-api-upload/{API_VERSION}/{container}",
         data=video_path.read_bytes(), timeout=600,
         headers={"Authorization": f"OAuth {tok}", "offset": "0", "file_size": str(size)})
    say("Instagram is processing the Reel")
    deadline = time.time() + PROCESS_WAIT
    while True:
        st = call("GET", f"{base}/{container}", {"fields": "status_code,status", "access_token": tok})
        code = st.get("status_code")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            raise InstagramError("Instagram couldn't process this video"
                                 + (f": {st['status']}" if st.get("status") else "") + ".")
        if time.time() > deadline:
            raise InstagramError("Instagram took too long to process the Reel. Try again later.")
        time.sleep(5)
    say("Publishing")
    media_id = call("POST", f"{base}/{info['ig_id']}/media_publish",
                    data={"creation_id": container, "access_token": tok})["id"]
    try:
        link = call("GET", f"{base}/{media_id}", {"fields": "permalink", "access_token": tok}).get("permalink", "")
    except InstagramError:
        link = ""
    return {"media_id": media_id, "permalink": link}
