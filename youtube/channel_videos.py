"""
The videos on a creator's YouTube channel, posted with Pit Crew or not (the Videos page and Shorts & Reels list them with a
YouTube link; web/channel_videos.py). Only the text a list needs is read, never the video itself (Developer Policies, gotcha 10).

Quota: 1 unit for the channel's uploads list, 1 per 50 videos for the list and 1 per 50 for their details, so a daily check
of the newest MAX_VIDEOS costs at most 21 units a channel.
"""
import re

MAX_VIDEOS = 500
SHORT_SECONDS = 180  # YouTube's longest Short
_TAG = re.compile(r"#shorts?\b", re.I)


def seconds_of(iso):
    """'PT1H2M3S' -> 3723."""
    m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", iso or "")
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def is_short(title, description, tags, seconds):
    """YouTube's API has no "this is a Short": #short or #shorts in the text or tags, or 3 minutes or less."""
    if _TAG.search(title or "") or _TAG.search(description or ""):
        return True
    if {str(t).strip().lstrip("#").lower() for t in tags or []} & {"short", "shorts"}:
        return True
    return 0 < seconds <= SHORT_SECONDS


def channel_videos(youtube):
    """The channel's public and unlisted videos, newest first: [{id, title, published, seconds, privacy, short}].
    Private ones, and live streams still to come or under way, are left out."""
    resp = youtube.channels().list(part="contentDetails", mine=True).execute()
    items = resp.get("items") or []
    if not items:
        return []
    uploads = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, token = [], None
    while len(ids) < MAX_VIDEOS:
        page = youtube.playlistItems().list(part="contentDetails", playlistId=uploads, maxResults=50, pageToken=token).execute()
        ids += [i["contentDetails"]["videoId"] for i in page.get("items", [])]
        token = page.get("nextPageToken")
        if not token:
            break
    out = []
    for k in range(0, min(len(ids), MAX_VIDEOS), 50):
        resp = youtube.videos().list(part="snippet,contentDetails,status", id=",".join(ids[k:k + 50])).execute()
        for it in resp.get("items", []):
            sn, st = it.get("snippet", {}), it.get("status", {})
            if st.get("privacyStatus") not in ("public", "unlisted") or sn.get("liveBroadcastContent") in ("live", "upcoming"):
                continue
            sec = seconds_of(it.get("contentDetails", {}).get("duration"))
            out.append({"id": it["id"], "title": sn.get("title", ""), "published": sn.get("publishedAt", ""), "seconds": sec,
                        "privacy": st["privacyStatus"], "short": is_short(sn.get("title"), sn.get("description"), sn.get("tags"), sec)})
    return out
