"""
Reading a vlog's public title, description and tags from its YouTube link.

Only the public text: Clipline never downloads videos from YouTube (YouTube's policies forbid it).
"""
import json
import os
import urllib.request

from youtube.links import video_id_from_url, youtube_link_problem


def _get_json(url, token=None):
    headers = {"User-Agent": "Clipline"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_video_info(url, token=None):
    """Title, description, tags and channel (name and @handle) of a public (or unlisted) YouTube video.

    Uses the YouTube Data API with YOUTUBE_API_KEY, or else with the creator's own YouTube connection
    (`token`, an OAuth access token), so connecting YouTube is enough. Without either, YouTube's public
    oEmbed lookup, which only gives the title and channel name.
    """
    problem = youtube_link_problem(url)
    vid = video_id_from_url(url)
    if problem or not vid:
        raise RuntimeError(problem or "That doesn't look like a YouTube video link.")
    key = os.getenv("YOUTUBE_API_KEY")
    if key or token:
        auth = {"key": key} if key else {}
        q = urllib.parse.urlencode({"part": "snippet", "id": vid, **auth})
        try:
            data = _get_json(f"https://www.googleapis.com/youtube/v3/videos?{q}", None if key else token)
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
                "tags": sn.get("tags", [])[:30], "channel": sn.get("channelTitle", ""),
                "channel_id": sn.get("channelId", ""),
                "channel_handle": channel_handle(sn.get("channelId", ""), key, token), "complete": True}
    q = urllib.parse.urlencode({"url": f"https://www.youtube.com/watch?v={vid}", "format": "json"})
    try:
        data = _get_json(f"https://www.youtube.com/oembed?{q}")
    except urllib.error.HTTPError as e:
        raise RuntimeError("YouTube couldn't find that video. Is it public or unlisted, not private?") from e
    except OSError as e:
        raise RuntimeError("Couldn't reach YouTube. Check your internet connection.") from e
    handle = urllib.parse.urlparse(data.get("author_url", "")).path.strip("/")
    return {"video_id": vid, "title": data.get("title", ""), "description": "", "tags": [],
            "channel": data.get("author_name", ""), "channel_handle": handle if handle.startswith("@") else "",
            "complete": False}


def channel_handle(channel_id, key=None, token=None):
    """The channel's @handle (e.g. "@sarahtravels"), or "" if it can't be looked up."""
    if not channel_id:
        return ""
    auth = {"key": key} if key else {}
    q = urllib.parse.urlencode({"part": "snippet", "id": channel_id, **auth})
    try:
        items = _get_json(f"https://www.googleapis.com/youtube/v3/channels?{q}", None if key else token).get("items")
    except OSError:
        return ""
    handle = ((items or [{}])[0].get("snippet") or {}).get("customUrl", "")
    return handle if handle.startswith("@") else ("@" + handle if handle else "")
