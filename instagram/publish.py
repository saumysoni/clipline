"""
Posting a Reel: make a container with the video's public address (Instagram downloads it from Pit Crew), wait until
Instagram has processed it, publish, and read back the Reel's link. Sending the bytes ("resumable upload") only works
for apps using Facebook Login for Business; with Instagram Login, Instagram answers "The parameter video_url is
required", so the video must be reachable at an https address (web/instagram_posting.py public_video_url).
Instagram has no scheduling for apps: Pit Crew's own scheduler (web/instagram_posting.py) calls post_reel
at the chosen time.
"""
import re
import time

from instagram.config import API_VERSION, GRAPH
from instagram.connection import is_professional, load
from instagram.http import InstagramError, call

PROCESS_WAIT = 15 * 60  # Instagram usually needs 30 s – 3 min to process a Reel
MAX_BYTES = 100 * 1024 * 1024
MAX_CAPTION = 2200  # Instagram's limits for a caption
MAX_TAGS = 30


def suggested_caption(it, vlog):
    """The caption Pit Crew writes when the creator hasn't written their own (hashtags not included): the title, then
    where the full video is. Not the hook: it's already on screen in the Reel, and under the title it read as the same
    line twice ("A Village With 700 Years of History" / "700 years of history?"). Links in captions can't be tapped on
    Instagram, so the full video is named."""
    parts = [it.get("title", "").strip()]
    vlog = vlog or {}
    # A YouTube @handle would tag whoever owns that name on Instagram, so it's written as the channel's address.
    handle = vlog.get("channel_handle") or ""
    where = f"youtube.com/{handle}" if handle.startswith("@") else vlog.get("channel") or ""
    if vlog.get("title"):
        parts.append(f"Full video on YouTube: \u201c{vlog['title']}\u201d" + (f" ({where})" if where else ""))
    elif where:
        parts.append(f"Full video on YouTube: {where}")
    return "\n\n".join(p for p in parts if p)


def caption_for(it, vlog):
    """The Reel caption as it's posted: the creator's caption (it["ig_caption"], from the card's Instagram tab) or the
    suggested one, then the Short's hashtags (shared with YouTube) and #reels, within Instagram's 30 hashtags (counting
    any typed into the caption) and 2,200 characters (the caption is shortened, never the hashtags)."""
    text = (it.get("ig_caption") or "").strip() or suggested_caption(it, vlog)
    have = {t.lower() for t in re.findall(r"#(\w+)", text)}  # hashtags typed into the caption count too
    tags, room_tags = [], MAX_TAGS - len(have)
    for t in [*(it.get("hashtags") or []), "reels"]:
        t = str(t).strip().lstrip("#")
        if t and t.lower() not in have and len(tags) < room_tags:
            tags.append(t); have.add(t.lower())
    line = " ".join("#" + t for t in tags)
    room = MAX_CAPTION - (len(line) + 2 if line else 0)
    if len(text) > room:
        text = text[:max(0, room - 1)].rstrip() + "…"
    return "\n\n".join(p for p in (text, line) if p)


def post_reel(user_id, video_path, video_url, caption, cover_ms=100, progress=None, ig_id=None, username=""):
    """Publish the video (video_path here, served at video_url for Instagram to download) as a Reel now, to the
    account ig_id (None: the active one). Returns {"media_id", "permalink"}. Raises InstagramError."""
    say = progress or (lambda *_: None)
    info = load(user_id, ig_id)
    if not info:
        if ig_id:
            who = f"@{username}" if username else "The Instagram account this Reel was planned for"
            raise InstagramError(f"{who} isn't connected to Pit Crew any more. Connect it again (Channels › Add "
                                 f"account), then press Try again.", expired=True)
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
                data={"media_type": "REELS", "video_url": video_url, "caption": caption,
                      "share_to_feed": "true", "thumb_offset": str(cover_ms), "access_token": tok})
    container = made["id"]
    say("Instagram is fetching and processing the Reel")
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
