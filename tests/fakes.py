"""
Stand-ins for everything outside Pit Crew, so tests run the real code with no internet, no API keys and no quota:

  AI          google.genai.Client is replaced: the real ai_json() / gemini_json() run and get answers shaped by each
              prompt (moments, hooks, thumbnails, vlog details, captions, the analytics read). AI.fail(...) makes the
              next calls fail like Gemini does (busy, limit, missing, bad key).
  YouTube     the youtube package's functions the web code calls, backed by an in-memory channel (VIDEOS), and a
              strict YouTube Analytics stand-in (the rules a real channel showed, CLAUDE.md gotcha 22b).
  Instagram   instagram.http.call, backed by an in-memory account (container -> FINISHED -> media_publish).
  Email       accounts.mail.send_email records into OUTBOX.
  Pipeline    fast() swaps transcription, editing and thumbnails for quick stand-ins (real files are written, the
              video is a few bytes); system tests leave the real pipeline in and only fake the AI and transcription.

install() is idempotent and called by every test file that needs it. reset() clears the in-memory state.
"""
from tests import _env  # noqa: F401  (first: throwaway folders)

import json
import os
import random
import re
import shutil
import subprocess
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

os.environ.update({  # (tests/_env.py removed every real setting first)
    "GEMINI_API_KEY": "fake-gemini-key", "INSTAGRAM_APP_ID": "123", "INSTAGRAM_APP_SECRET": "test-secret",
    "SMTP_HOST": "fake-smtp", "APP_URL": "https://pitcrew.test", "PUBLIC_URL": "https://pitcrew.test",
})

TMP = _env.TMP
_INSTALLED = False
_LOCK = threading.Lock()


# ---------------------------------------------------------------- AI ------------------------------------------------

class _GeminiError(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


class FakeAI:
    """Answers by prompt. calls: every prompt asked (kind, model). fail(code, msg, times): next calls raise."""

    def __init__(self):
        self.calls, self.failures, self.bad_numbers = [], [], False

    def fail(self, code, msg, times=1):
        self.failures += [(code, msg)] * times

    def reset(self):
        self.calls, self.failures, self.bad_numbers = [], [], False

    def kinds(self):
        return [k for k, _ in self.calls]

    # the client google.genai.Client(api_key, http_options) returns
    def client(self, *a, **k):
        ai = self

        class Models:
            def generate_content(self, model, contents, config=None):
                return ai.answer(model, contents)
        return SimpleNamespace(models=Models())

    def answer(self, model, contents):
        text = contents if isinstance(contents, str) else "\n".join(c for c in contents if isinstance(c, str))
        kind = self.kind(text)
        with _LOCK:
            self.calls.append((kind, model))
            if self.failures:
                code, msg = self.failures.pop(0)
                raise _GeminiError(code, msg)
        return SimpleNamespace(text=json.dumps(getattr(self, "_" + kind)(text)))

    @staticmethod
    def kind(text):
        for key, kind in (("Return ONLY a JSON array of exactly", "moments"), ("The creator chose this moment", "manual"),
                          ("Decide what they want", "again"), ("You write on-screen hooks", "hooks"),
                          ("thumbnail for a YouTube Short", "thumb"), ("full YouTube vlog (landscape", "vthumb"),
                          ("helping a YouTube vlogger upload a full vlog", "meta"), ("analytics coach", "coach"),
                          ("You are shortening a YouTube Short", "shorten")):
            if key in text:
                return kind
        if '{"items"' in text or "\"items\"" in text:
            return "items"
        raise ValueError("FakeAI doesn't know this prompt: " + text[:200])

    @staticmethod
    def _segments(text):
        return [(float(a), float(b)) for a, b in re.findall(r"^\[(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)\]", text, flags=re.M)]

    @staticmethod
    def _text(start=0):
        return {"hooks": {"curiosity": "Wait for the ending", "bold": "This changed everything", "story": "So this happened"},
                "hook_pick": "curiosity", "title": f"The moment at {int(start)} seconds", "thumb_line1": "",
                "thumb_line2": "BIG DAY", "why": "It has a clear payoff.", "hashtags": ["vlog", "travel", "shorts"]}

    def _moments(self, text):
        n = int(re.search(r"exactly (\d+) objects", text).group(1))
        segs = self._segments(text)
        end = segs[-1][1] if segs else 300
        out, t = [], 2.0
        while len(out) < n and t + 30 <= end:
            out.append({"start": t, "end": t + 30, **self._text(t)})
            t += 45
        return out

    def _manual(self, text):
        return self._text()

    def _again(self, text):
        """A 30-second moment clear of every span the prompt mentions (the other Shorts, ones already tried)."""
        segs = self._segments(text)
        end = segs[-1][1] if segs else 300
        busy = [(float(a), float(b)) for a, b in re.findall(r"(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)s\b", text)]
        t = 1.0
        while t + 30 <= end and any(t < b and a < t + 30 for a, b in busy):
            t += 2.5
        return {"change": "new", "options": [{"start": t, "end": t + 30, **self._text(t)}]}

    def _hooks(self, text):
        return {"hooks": {"curiosity": "You won't guess this", "bold": "Best decision ever", "story": "It started here"},
                "hook_pick": "bold"}

    def _thumb(self, text):
        return {"frame": 1, "focus": [200, 300, 700, 700], "line1": "", "line2": "BIG DAY", "accent": "#FFD60A"}

    _vthumb = _thumb

    def _meta(self, text):
        return {"titles": ["A day in the hills", "We got lost (in a good way)", "The best food of the trip"],
                "description": "We drove into the hills and found a market.\n\nWatch till the end for the view.",
                "chapters": [{"t": 0, "title": "Intro"}, {"t": 30, "title": "The road"}, {"t": 60, "title": "Market"},
                             {"t": 90, "title": "The view"}],
                "tags": ["travel vlog", "hills", "road trip", "street food", "market", "india", "vlog", "day trip"],
                "hashtags": ["travel", "vlog", "india"], "thumb_line1": "WE GOT", "thumb_line2": "LOST"}

    @staticmethod
    def _sentences(text):
        """(number, seconds) of each numbered sentence in an AI Edit prompt."""
        return [(int(k), float(d)) for k, d in re.findall(r"^\[(\d+)\] \([\d:]+, ([\d.]+)s\)", text, flags=re.M)]

    def _shorten(self, text):
        """Skips the first sentence (so a test can tell the AI chose), then keeps sentences up to the target."""
        target = float(re.search(r"to about (\d+) seconds", text).group(1))
        keep, total = [], 0.0
        for k, d in self._sentences(text)[1:]:
            if total >= target * 0.9:
                break
            keep.append(k)
            total += d
        return {"keep": keep, "why": "Cut the slow start."}

    def _items(self, text):
        return {"items": ["The view was worth it", "Lost in the best way", "One road, one market, one view"]}

    def _coach(self, text):
        bad = " and 12,345 new fans" if self.bad_numbers else ""
        return {"headline": "Your clips are finding new viewers" + bad + ".", "headline_youtube": "YouTube likes your Shorts.",
                "headline_instagram": "Your Reels are reaching people.",
                "tips": [{"platform": "youtube", "title": "Name the place", "because": "Search brings viewers.",
                          "try": "Put the place in the title."},
                         {"platform": "youtube", "title": "Post often", "because": "Views come in the first days.",
                          "try": "Post one clip every two days."},
                         {"platform": "instagram", "title": "Ask a question", "because": "Comments start talks.",
                          "try": "End the caption with a question."},
                         {"platform": "instagram", "title": "Use the cover", "because": "Covers get taps.",
                          "try": "Pick a bright cover frame."}]}


AI = FakeAI()


# ---------------------------------------------------------------- YouTube -------------------------------------------

VIDEOS = {}  # id -> {title, channel, publish_at (aware dt or None), published (date), kind, peak, privacy, hidden}
UPLOADED = []  # (channel, title, description, tags, file size) in order


def _vid(prefix="pc"):
    return prefix + "".join(random.choice("abcdefghijkmnpqrstuvwxyz0123456789") for _ in range(9))


class FakeService:
    def __init__(self, uid, channel):
        self.uid, self.channel = uid, channel


def yt_account(uid):
    from accounts import db
    rows = [r for r in db.connections(uid, "youtube") if r["account_id"]]
    chans = [{**(r["profile"] or {"id": r["account_id"], "title": "", "handle": "", "thumb": ""}), "active": r["active"]}
             for r in rows]
    active = next((c for c in chans if c["active"]), None)
    return {"configured": True, "signed_in": bool(active), "channel": active, "channels": chans, "offline": False}


def yt_get_service(uid, channel=None):
    from youtube.connection import NOT_CONNECTED
    acct = yt_account(uid)
    if channel and channel not in {c["id"] for c in acct["channels"]}:
        raise RuntimeError(NOT_CONNECTED)
    ch = channel or (acct["channel"] or {}).get("id")
    if not ch:
        raise RuntimeError("Your YouTube channel isn't connected. Click Connect YouTube, then try again.")
    return FakeService(uid, ch)


def yt_upload_short(service, path, title, desc, tags, publish_at=None, thumb_path=None, progress=lambda p: None):
    size = Path(path).stat().st_size
    assert size > 0, "uploading an empty file"
    for p in (0, 50, 100):
        progress(p)
    v = _vid()
    VIDEOS[v] = {"title": title, "channel": service.channel, "publish_at": publish_at, "desc": desc,
                 "published": (publish_at or datetime.now(timezone.utc)).date(), "kind": "shorts",
                 "privacy": "private" if publish_at else "public"}
    UPLOADED.append((service.channel, title, desc, list(tags or []), size))
    return v, None


def yt_upload_vlog(service, path, title, desc, tags, privacy="public", publish_at=None, thumb_path=None,
                   progress=lambda p: None):
    v = _vid("pcvlog")
    VIDEOS[v] = {"title": title, "channel": service.channel, "publish_at": publish_at, "desc": desc,
                 "published": (publish_at or datetime.now(timezone.utc)).date(), "kind": "videoOnDemand",
                 "privacy": privacy}
    UPLOADED.append((service.channel, title, desc, list(tags or []), Path(path).stat().st_size))
    progress(100)
    return v, None


def yt_video_states(service, ids):
    out, now = {}, datetime.now(timezone.utc)
    for i in ids:
        v = VIDEOS.get(i)
        if not v or v.get("hidden") or v.get("channel") not in (None, service.channel):
            continue
        pa = v.get("publish_at")
        if pa and pa > now:
            out[i] = {"privacy": "private", "publish_at": pa.isoformat().replace("+00:00", "Z"), "title": v["title"]}
        else:
            out[i] = {"privacy": v.get("privacy") if v.get("privacy") == "unlisted" else "public", "publish_at": None,
                      "title": v["title"]}
    return out


def yt_reschedule(service, vid, when):
    VIDEOS[vid]["publish_at"] = when


def yt_update_title(service, vid, title):
    VIDEOS[vid]["title"] = title


def yt_delete_video(service, vid):
    VIDEOS.pop(vid, None)


def yt_fetch_video_info(url, token=None):
    from youtube.links import video_id_from_url
    vid = video_id_from_url(url)
    if vid == "missingvid1":
        raise RuntimeError("YouTube couldn't find that video. Is it public or unlisted, not private?")
    return {"video_id": vid, "title": "My trip to the hills", "description": "A day in the hills.", "tags": ["hills"],
            "channel": "Test Channel", "channel_id": "UCtest", "channel_handle": "@test", "complete": True}


REVOKED = []  # tokens Pit Crew asked Google to revoke


def yt_sign_out(uid, channel=None):
    from accounts import db
    row = db.connection(uid, "youtube", channel)
    if row:
        REVOKED.append(row["account_id"])
        db.drop_connection(row["id"])


def connect_youtube(uid, channel="UCchannel000000000000001", title="Test Channel", handle="@test"):
    from accounts import db
    db.save_connection(uid, "youtube", channel, {"token": "t", "refresh_token": "r", "scopes": []},
                       {"id": channel, "title": title, "handle": handle, "thumb": ""})
    return channel


# The strict YouTube Analytics stand-in: every number is a sum of per-video, per-day views, so any range, content
# filter and breakdown agree with each other. Rules from a real channel: camelCase creatorContentType values,
# video+creatorContentType together -> 400, subscribedStatus -> 500, numbers end 2 days before today.
KINDS = {"shorts", "videoOnDemand", "liveStream", "story"}
SPLITS = {
    "country": [("IN", .42), ("US", .3), ("GB", .12), ("AU", .06), ("CA", .05)],
    "deviceType": [("MOBILE", .86), ("DESKTOP", .08), ("TABLET", .04), ("TV", .02)],
    "operatingSystem": [("ANDROID", .58), ("IOS", .33), ("WINDOWS", .06), ("MACINTOSH", .03)],
    "insightPlaybackLocationType": [("SHORTS_FEED", .9), ("WATCH", .06), ("CHANNEL", .03), ("EMBEDDED", .01)],
    "insightTrafficSourceType": [("SHORTS", .78), ("YT_SEARCH", .12), ("SUBSCRIBER", .05), ("YT_CHANNEL", .03),
                                 ("EXT_URL", .02)],
    "insightTrafficSourceDetail": [("hill market", .03), ("road trip", .015)],
    "city": [("Guwahati", .03), ("Los Angeles", .02), ("Mumbai", .015)],
    "sharingService": [("WHATSAPP", .004), ("COPY_PASTE", .002)],
}
ANALYTICS_CALLS = []


class _Q:
    def __init__(self, f):
        self.f = f

    def execute(self, **k):
        return self.f()


def _http_error(status, msg):
    import httplib2
    from googleapiclient.errors import HttpError
    raise HttpError(httplib2.Response({"status": status}), json.dumps({"error": {"code": status, "message": msg}}).encode())


def day_views(v, d):
    m = VIDEOS.get(v, {})
    p = m.get("published")
    if not p or d < p or d > date.today() - timedelta(days=2):
        return 0
    peak = m.get("peak") or (900 if m.get("kind", "shorts") == "shorts" else 400)
    return int(peak * (0.62 ** (d - p).days) + peak * 0.02 + random.Random(f"{v}{d}").randint(0, 6))


def live_views(v):
    p = VIDEOS.get(v, {}).get("published")
    if not p:
        return 0
    return sum(day_views(v, p + timedelta(i)) for i in range((date.today() - p).days + 1)) + \
        2 * ((VIDEOS[v].get("peak") or 900) // 40)


def _report(**q):
    ANALYTICS_CALLS.append(q)
    m = q["metrics"].split(",")
    dims = q["dimensions"].split(",") if q.get("dimensions") else []
    f = {}
    for part in [x for x in (q.get("filters") or "").split(";") if x]:
        k, _, v = part.partition("==")
        f[k] = v
    if "creatorContentType" in f and f["creatorContentType"] not in KINDS:
        _http_error(400, f"Invalid value ({f['creatorContentType']}) given in field parameters.filters.")
    if "video" in dims and "creatorContentType" in dims:
        _http_error(400, "The query is not supported.")
    if "subscribedStatus" in dims:
        _http_error(500, "An internal error has occurred.")
    s0, e0 = date.fromisoformat(q["startDate"]), date.fromisoformat(q["endDate"])
    if e0 < s0:
        _http_error(400, "The start date must be on or before the end date.")
    days = [s0 + timedelta(i) for i in range((e0 - s0).days + 1)]
    vids = [v for v in VIDEOS if VIDEOS[v].get("published")]
    if "video" in f:
        vids = [v for v in vids if v in f["video"].split(",")]
    if "creatorContentType" in f:
        vids = [v for v in vids if VIDEOS[v].get("kind", "shorts") == f["creatorContentType"]]

    def metrics(views, vl):
        long = vl and all(VIDEOS[v].get("kind") == "videoOnDemand" for v in vl)
        r = {"views": views, "engagedViews": int(views * 0.41), "likes": views // 70, "comments": views // 900,
             "shares": views // 400, "subscribersGained": views // 800, "subscribersLost": views // 5000,
             "estimatedMinutesWatched": round(views * (6.5 if long else 0.18)),
             "averageViewDuration": (410.0 if long else 14.0) if views else 0,
             "averageViewPercentage": (46.0 if long else 53.4) if views else 0, "viewerPercentage": 0}
        return [r.get(x, 0) for x in m]
    V = lambda vl, dl: sum(day_views(v, d) for v in vl for d in dl)  # noqa: E731
    mk = lambda rows: _Q(lambda: {"columnHeaders": [{"name": n} for n in dims + m], "rows": rows})  # noqa: E731
    if not dims:
        return mk([metrics(V(vids, days), vids)])
    if dims == ["day"]:
        return mk([[str(d)] + metrics(V(vids, [d]), vids) for d in days if d <= date.today() - timedelta(days=2)])
    if dims == ["video"]:
        rows = sorted(([v] + metrics(V([v], days), [v]) for v in vids if not VIDEOS[v].get("hidden")), key=lambda r: -r[1])
        return mk([r for r in rows if r[1] > 0][: int(q.get("maxResults") or 200)])
    if dims[-1:] == ["creatorContentType"]:
        rows = []
        for k in sorted(KINDS):
            vl = [v for v in vids if VIDEOS[v].get("kind", "shorts") == k]
            if not vl:
                continue
            if dims == ["creatorContentType"]:
                if V(vl, days):
                    rows.append([k] + metrics(V(vl, days), vl))
            elif dims[0] == "day":
                rows += [[str(d), k] + metrics(V(vl, [d]), vl) for d in days if V(vl, [d])]
            elif dims[0] in SPLITS:
                n = V(vl, days)
                rows += [[key, k] + metrics(int(n * sh), vl) for key, sh in SPLITS[dims[0]] if int(n * sh)]
        return mk(rows)
    if dims == ["elapsedVideoTimeRatio"]:
        return mk([[r / 100, 1.2 - 0.008 * r, 0.42] for r in range(1, 101)])
    if dims == ["ageGroup", "gender"]:
        if not V(vids, days):
            return mk([])
        return mk([["age18-24", "female", 14.0], ["age18-24", "male", 22.0], ["age25-34", "female", 18.0],
                   ["age25-34", "male", 30.0], ["age35-44", "male", 16.0]])
    if len(dims) == 1 and dims[0] in SPLITS:
        n = V(vids, days)
        if m[0] == "shares":
            return mk([[k, max(1, int(n * sh))] for k, sh in SPLITS[dims[0]] if n])
        return mk([[k, int(n * sh)] + [0] * (len(m) - 1) for k, sh in SPLITS[dims[0]] if int(n * sh)])
    raise ValueError(f"FakeAnalytics doesn't know dimensions {dims}")


class _YA:
    def reports(self):
        return self

    def query(self, **q):
        return _report(**q)


class _YT3:
    def __init__(self, channel):
        self.channel = channel

    def channels(self):
        return self

    def videos(self):
        return self

    def list(self, **k):
        if "mine" in k or "id" not in k:
            return _Q(lambda: {"items": [{"id": self.channel, "snippet": {"title": "Test Channel", "thumbnails": {},
                                                                          "publishedAt": "2024-09-15T23:56:23Z"},
                                          "statistics": {"subscriberCount": "12840"}}]})
        out = []
        for i in k["id"].split(","):
            v = VIDEOS.get(i)
            if not v or v.get("hidden"):
                continue
            n = live_views(i)
            out.append({"id": i, "snippet": {"title": v["title"], "publishedAt": f"{v['published']}T18:00:00Z",
                                             "thumbnails": {}},
                        "statistics": {"viewCount": str(n), "likeCount": str(n // 70), "commentCount": str(n // 900)},
                        "contentDetails": {"duration": "PT55S" if v.get("kind", "shorts") == "shorts" else "PT14M10S"},
                        "status": {"privacyStatus": "public"}})
        return _Q(lambda: {"items": out})


def yt_services(uid, channel=None):
    acct = yt_account(uid)
    ch = channel or (acct["channel"] or {}).get("id")
    if not ch:
        from youtube.analytics import NeedsReconnect
        raise NeedsReconnect("Connect YouTube to see analytics.")
    return _YT3(ch), _YA()


def age_uploads(job_id, days=(14, 12, 10, 4, 2)):
    """Pretend a job's posted Shorts went out days ago, so Analytics has history."""
    from web.store import LOCK, load_job, update
    with LOCK:
        job = load_job(job_id)
    ups = []
    for k, u in enumerate(job.get("uploads") or []):
        when = datetime.now(timezone.utc) - timedelta(days=days[k % len(days)])
        ups.append({**u, "when": when.isoformat(), "uploaded_at": when.isoformat()})
        if u.get("video_id") in VIDEOS:
            VIDEOS[u["video_id"]].update(publish_at=when, published=when.date())
    update(job_id, uploads=ups)


# ---------------------------------------------------------------- Instagram -----------------------------------------

REELS = {}  # media id -> {caption, ig_id, posted (dt)}
IG_CONTAINERS = {}  # container id -> {video_url, caption, polls}
IG = SimpleNamespace(fail_publish=None, container_polls=1, refreshed=0, account_type="MEDIA_CREATOR", deleted_reels=set(),
                     permissions="instagram_business_basic,instagram_business_content_publish,"
                                 "instagram_business_manage_insights")


def connect_instagram(uid, ig_id="1789", username="pitcrew.test", account_type="MEDIA_CREATOR", days_left=50):
    from accounts import db
    db.save_connection(uid, "instagram", ig_id, {"token": "t", "expires_at": int(time.time()) + days_left * 86400,
                                                 "ig_id": ig_id, "username": username, "account_type": account_type,
                                                 "picture": "", "name": "Test"}, {"username": username})
    return ig_id


def ig_call(method, url, params=None, data=None, headers=None, timeout=30):
    from instagram.http import InstagramError
    p = {**(params or {}), **(data if isinstance(data, dict) else {})}
    u = url.split("?")[0]
    parts = u.rstrip("/").split("/")
    last = parts[-1]
    if u.endswith("/oauth/access_token"):
        if p.get("code") == "bad":
            raise InstagramError("Invalid authorization code")
        return {"access_token": "short-token", "user_id": 1789, "permissions": IG.permissions}
    if last == "access_token":
        return {"access_token": "long-token", "expires_in": 5184000}
    if last == "refresh_access_token":
        IG.refreshed += 1
        return {"access_token": "refreshed-token", "expires_in": 5184000}
    if last == "me":
        if "followers_count" in p.get("fields", ""):
            return {"followers_count": 8421, "media_count": len(REELS)}
        return {"user_id": "1789", "username": "pitcrew.test", "account_type": IG.account_type, "profile_picture_url": ""}
    if last == "media" and method == "POST":
        if not p.get("video_url", "").startswith("https://"):
            raise InstagramError("The parameter video_url is required")
        cid = "C" + str(len(IG_CONTAINERS) + 1)
        IG_CONTAINERS[cid] = {"video_url": p["video_url"], "caption": p.get("caption", ""), "polls": 0, "ig_id": parts[-2]}
        return {"id": cid}
    if last in IG_CONTAINERS:
        c = IG_CONTAINERS[last]
        c["polls"] += 1
        return {"status_code": "FINISHED" if c["polls"] >= IG.container_polls else "IN_PROGRESS"}
    if last == "media_publish":
        if IG.fail_publish:
            msg, IG.fail_publish = IG.fail_publish, None
            raise InstagramError(msg)
        c = IG_CONTAINERS[p["creation_id"]]
        mid = f"M{len(REELS) + 1}{random.randint(100, 999)}"
        REELS[mid] = {"caption": c["caption"], "ig_id": c["ig_id"], "posted": datetime.now(timezone.utc)}
        return {"id": mid}
    if method == "GET" and last in IG.deleted_reels:  # deleted in the Instagram app
        raise InstagramError("Instagram said: Object with ID '%s' does not exist" % last, 100)
    if last in REELS and method == "GET" and "insights" not in u:
        return {"permalink": f"https://www.instagram.com/reel/{last}/", "id": last}
    if last == "media" and method == "GET":
        return {"data": [{"id": m, "media_product_type": "REELS", "caption": r["caption"], "like_count": 90,
                          "comments_count": 4, "permalink": f"https://www.instagram.com/reel/{m}/", "thumbnail_url": "",
                          "timestamp": r["posted"].strftime("%Y-%m-%dT%H:%M:%S+0000")} for m, r in REELS.items()]}
    if last == "insights" and parts[-2] in REELS:
        v = 2400
        return {"data": [{"name": n, "values": [{"value": x}]} for n, x in (
            ("views", v), ("reach", int(v * .72)), ("likes", 90), ("comments", 4), ("shares", v // 90),
            ("saved", v // 60), ("ig_reels_avg_watch_time", 5200), ("total_interactions", 150))]}
    if last == "insights":
        met, bd = p.get("metric", ""), p.get("breakdown")
        if p.get("since") and int(p["until"]) - int(p["since"]) > 30 * 86400 + 3600:
            raise InstagramError("(#100) The time range for since and until can't be greater than 30 days")
        frac = (int(p["until"]) - int(p["since"])) / (30 * 86400) if p.get("since") else 1

        def tv(name, value, results=None):
            d = {"name": name, "total_value": {"value": value}}
            if results:
                d["total_value"]["breakdowns"] = [{"dimension_keys": [bd], "results": [
                    {"dimension_values": [k], "value": x} for k, x in results]}]
            return d
        if p.get("metric_type") == "time_series":
            n = round((int(p["until"]) - int(p["since"])) / 86400)
            return {"data": [{"name": "reach", "values": [{"value": 1800, "end_time": datetime.fromtimestamp(
                int(p["since"]) + (i + 1) * 86400, timezone.utc).strftime("%Y-%m-%dT07:00:00+0000")} for i in range(n)]}]}
        if met == "online_followers":
            return {"data": [{"name": met, "values": [{"value": {str(h): 300 + 40 * h for h in range(24)}}]}]}
        if bd == "follow_type":
            if met == "follows_and_unfollows":
                return {"data": [tv(met, 8, [("FOLLOWER", 6), ("NON_FOLLOWER", 2)])]}
            return {"data": [tv(met, round(60000 * frac), [("FOLLOWER", round(14200 * frac)),
                                                         ("NON_FOLLOWER", round(45800 * frac))])]}
        if bd == "contact_button_type":
            return {"data": [tv(met, 120, [("UNDEFINED", 120)])]}
        if "demographics" in met:
            r = {"country": [("IN", 3100), ("GB", 1200), ("US", 900)], "city": [("Mumbai, Maharashtra", 700)],
                 "age": [("18-24", 1800), ("25-34", 2600)], "gender": [("F", 3100), ("M", 2400)]}[bd]
            return {"data": [tv(met, None, r)]}
        tot = {"views": 98000, "reach": 31000, "accounts_engaged": 4100, "total_interactions": 7600, "likes": 5900,
               "comments": 310, "shares": 820, "saves": 570, "profile_links_taps": 120}
        return {"data": [tv(k, round(tot[k] * frac)) for k in met.split(",") if k in tot]}
    raise ValueError(f"FakeInstagram doesn't know {method} {u}")


# ---------------------------------------------------------------- email ---------------------------------------------

OUTBOX = []  # (to, subject, text)


def fake_send_email(to, subject, text):
    OUTBOX.append((to, subject, text))


def wait_for_mail(to, contains="", timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        for m in OUTBOX:
            if m[0] == to and contains in m[1] + m[2]:
                return m
        time.sleep(0.02)
    raise AssertionError(f"No email to {to} containing {contains!r}. Sent: {[(m[0], m[1]) for m in OUTBOX]}")


def link_token(text, kind):
    return re.search(rf"#{kind}=([\w-]+)", text).group(1)


# ---------------------------------------------------------------- media ---------------------------------------------

def test_video(seconds=150, size="320x180", name=None, plain=False):
    """A real video (moving test picture + a tone), made once per test run and copied where asked."""
    import tempfile
    cache = Path(os.getenv("PITCREW_TEST_MEDIA") or Path(tempfile.gettempdir()) / f"pitcrew-test-media-{os.getuid()}")
    out = cache / (name or f"vlog_{seconds}s_{size}{'_plain' if plain else ''}.mp4")
    picture = (f"color=c=0x203040:size={size}:rate=30,noise=alls=10:allf=t" if plain  # no yellow anywhere in it
               else f"testsrc2=size={size}:rate=30")
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        from pipeline.ffmpeg import ffmpeg_exe
        subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", picture,
                        "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000", "-t", str(seconds),
                        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "32", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
                        str(out) + ".part.mp4"], check=True)
        os.replace(str(out) + ".part.mp4", out)  # never a half-made file if two runs make it at once
    return out


def transcript_for(seconds):
    """A transcript like faster-whisper's: a word every 0.4 s, sentences of about 5 s."""
    words, t, k = [], 0.5, 0
    vocab = "so we drove up into the hills and found this market where they sell the best tea in town".split()
    while t + 0.4 <= seconds - 0.5:
        words.append({"w": vocab[k % len(vocab)], "s": round(t, 2), "e": round(t + 0.32, 2)})
        t += 0.4
        k += 1
    segs = []
    for i in range(0, len(words), 12):
        chunk = words[i:i + 12]
        segs.append({"s": chunk[0]["s"], "e": chunk[-1]["e"], "text": " ".join(w["w"] for w in chunk) + "."})
    return {"words": words, "segments": segs, "duration": float(seconds), "language": "en", "engine": "fake"}


SLOW = SimpleNamespace(transcribe=float(os.getenv("PITCREW_FAKE_SLOW") or 0), fail="", render=0.0)  # env: for the server process


def fake_transcribe(video_path, out_json, progress=lambda pct, msg: None):
    out_json = Path(out_json)
    from pipeline.ffmpeg import probe
    end = time.time() + SLOW.transcribe  # SLOW.transcribe > 0: a vlog that takes a while (Stop, queue tests)
    while True:
        progress(50, "Listening to the vlog")  # (each progress report is where Stop takes effect)
        if time.time() >= end:
            break
        time.sleep(0.02)
    if SLOW.fail:
        raise RuntimeError(SLOW.fail)
    if out_json.exists():  # a saved transcript (same video as before): used as it is
        return json.loads(out_json.read_text(encoding="utf-8"))
    tr = transcript_for(probe(video_path)["duration"])
    out_json.write_text(json.dumps(tr), encoding="utf-8")
    return tr


def _jpeg(path, size=(1080, 1920), color=(200, 40, 60)):
    from PIL import Image
    Image.new("RGB", size, color).save(path, "JPEG", quality=80)


RENDERED = []  # what each fast_render was asked to make (AI Edit tests)


def fast_render(video_path, meta, moment, words, idx, style, job_dir, cx="find"):
    from pipeline.captions import build_ass
    from pipeline.pieces import kept, timeline
    job_dir = Path(job_dir)
    RENDERED.append({"idx": idx, "pieces": kept(moment), "hook": moment.get("hook", ""), "hook_mode": moment.get("hook_mode")})
    time.sleep(SLOW.render)  # SLOW.render > 0: editing takes a while (Pause tests)
    build_ass(timeline(moment, words), 0.0, sum(b - a for a, b in kept(moment)), moment.get("hook", ""), style,
              job_dir / f"captions_{idx}.ass")
    (job_dir / f"short_{idx}.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + os.urandom(64))
    return f"short_{idx}.mp4", None if cx == "find" else cx


THUMB_AVOIDED = []  # the last thumbnail's plan each Try again asked to avoid


def fast_thumbnail(video_path, meta, moment, cx, idx, job_dir, words=None, context=None, avoid=None):
    THUMB_AVOIDED.append(avoid)
    _jpeg(Path(job_dir) / f"thumb_{idx}.jpg")
    return f"thumb_{idx}.jpg"


def fast_vlog_thumbnail(video_path, duration, job_dir, title="", line1="", line2="", look=None):
    _jpeg(Path(job_dir) / "vthumb_1.jpg", (1280, 720))
    return "vthumb_1.jpg"


def fast():
    """Swap the slow pipeline steps for quick stand-ins (unit and flow tests)."""
    import pipeline
    pipeline.transcribe = fake_transcribe
    pipeline.render_short = fast_render
    pipeline.make_thumbnail = fast_thumbnail
    pipeline.make_vlog_thumbnail = fast_vlog_thumbnail
    pipeline.retext_thumbnail = lambda v, m, mo, cx, num, d: (fast_thumbnail(v, m, mo, cx, num, d), None)
    pipeline.plays_everywhere = lambda src, meta: True
    pipeline.covered_video = lambda job_dir, video, thumb: Path(job_dir) / video
    pipeline.make_poster = lambda *a, **k: None


def real_media():
    """System tests: the real pipeline, with only transcription faked (no speech model here)."""
    import pipeline
    pipeline.transcribe = fake_transcribe


# ---------------------------------------------------------------- install -------------------------------------------

def install():
    """Patch everything once (before or after importing app; the web code looks these up when it calls them)."""
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    import google.genai
    google.genai.Client = AI.client
    import pipeline.ai
    pipeline.ai.BUSY_WAITS = [0.01, 0.01]  # same rounds as the real [15, 45], without the waiting
    import pipeline.thumbnails.plan as TP
    TP.REST = 0.01

    import youtube
    import youtube.analytics as YA
    for name, fn in (("account", yt_account), ("get_service", yt_get_service), ("upload_short", yt_upload_short),
                     ("upload_vlog", yt_upload_vlog), ("video_states", yt_video_states), ("reschedule", yt_reschedule),
                     ("update_title", yt_update_title), ("delete_video", yt_delete_video),
                     ("fetch_video_info", yt_fetch_video_info), ("sign_out", yt_sign_out)):
        setattr(youtube, name, fn)
    youtube.is_configured = lambda: True
    youtube.access_token = lambda uid, channel=None: "tok" if yt_account(uid)["signed_in"] else None
    YA._services = yt_services

    import instagram.account_insights as IA
    import instagram.connection as IC
    import instagram.http as IH
    import instagram.insights as II
    import instagram.publish as IP
    IH.call = IC.call = IP.call = II.call = ig_call
    IA.http.call = ig_call
    import instagram.config as ICONF
    ICONF.is_configured = lambda: True

    import accounts.mail as M
    M.send_email = fake_send_email


def reset():
    """Forget the in-memory outside world (between tests that need a clean one)."""
    AI.reset()
    VIDEOS.clear()
    UPLOADED.clear()
    REVOKED.clear()
    REELS.clear()
    IG_CONTAINERS.clear()
    IG.fail_publish, IG.container_polls, IG.refreshed, IG.account_type = None, 1, 0, "MEDIA_CREATOR"
    IG.deleted_reels.clear()
    IG.permissions = "instagram_business_basic,instagram_business_content_publish,instagram_business_manage_insights"
    OUTBOX.clear()
    RENDERED.clear()
    ANALYTICS_CALLS.clear()
    SLOW.transcribe, SLOW.fail, SLOW.render = 0.0, "", 0.0
    from web import accounts as WA
    WA.FAILS.clear()
    WA.SIGNUPS.clear()
    for mod in ("youtube.analytics", "youtube.analytics_more", "youtube.analytics_coach", "instagram.insights",
                "instagram.account_insights"):
        import importlib
        m = importlib.import_module(mod)
        getattr(m, "_CACHE", {}).clear()
    import youtube.analytics as YA
    YA._WEEK.clear()
    import web.youtube_sync as YS
    YS._LAST.clear()


# ---------------------------------------------------------------- app helpers ---------------------------------------

def app():
    install()
    fast() if os.getenv("PITCREW_REAL_MEDIA") != "1" else real_media()
    import app as pitcrew  # noqa: F401  (registers every route; starts the queue and the Instagram scheduler)
    from web.server import app as flask_app
    flask_app.testing = True
    return flask_app


def new_user(email=None, password="password-123", verified=True, name="Test"):
    from accounts import db
    from werkzeug.security import generate_password_hash
    db.init()
    email = email or f"u{time.time_ns()}@example.com"
    uid = db.create_user(email, name, password_hash=generate_password_hash(password, method="pbkdf2:sha256:1000"),
                         email_verified=verified)
    return db.user_by_id(uid)


def client(user=None):
    """A test client, signed in as `user` (a db row) if given."""
    c = app().test_client()
    if user:
        with c.session_transaction() as s:
            s["uid"], s["sv"] = user["id"], user["session_version"]
    return c


def wait(fn, timeout=20, every=0.05, what="condition"):
    """Poll fn() until it's truthy; returns its value."""
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(every)
    raise AssertionError(f"Timed out waiting for {what}")


def upload(c, path, piece=8 * 1024 * 1024):
    """Send a file through /api/upload in pieces, as the page does. Returns the upload id."""
    data = Path(path).read_bytes()
    r = c.post("/api/upload/new", json={"name": Path(path).name, "size": len(data)})
    assert r.status_code == 200, r.get_json()
    uid = r.get_json()["id"]
    off = 0
    while off < len(data):
        r = c.post(f"/api/upload/{uid}?offset={off}", data=data[off:off + piece],
                   headers={"Content-Type": "application/octet-stream"})
        assert r.status_code == 200, r.get_json()
        off = r.get_json()["received"]
    return uid


def job_json(job_id):
    """The job as Pit Crew holds it (memory, else its job.json), read under the job lock."""
    from web.store import LOCK, load_job
    with LOCK:
        return json.loads(json.dumps(load_job(job_id), default=str))


def wait_ready(c, job_id, timeout=60):
    def done():
        j = c.get(f"/api/status/{job_id}").get_json() or {}
        return j if j.get("status") in ("ready", "error") else None
    return wait(done, timeout, 0.1, f"vlog {job_id} to finish")


def make_shorts(c, seconds=150, count=3, **form):
    """Upload a generated vlog and make Shorts from it. Returns (job id, status JSON)."""
    up = upload(c, test_video(seconds))
    r = c.post("/api/start", data={"count": str(count), "style": "bold", "upload": up, "tz": "UTC", **form})
    assert r.status_code == 200, r.get_json()
    jid = r.get_json()["id"]
    st = wait_ready(c, jid)
    assert st["status"] == "ready", st
    return jid, st


def copy_into(job_id, src, name):
    from settings import JOBS_DIR
    shutil.copy(src, JOBS_DIR / job_id / name)
