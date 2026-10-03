"""
Reading a vlog's public title, description and tags from its YouTube link.

Only the public text: Clipline never downloads videos from YouTube (YouTube's policies forbid it).
"""
import json
import os
import urllib.request

from youtube.links import video_id_from_url, youtube_link_problem


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
