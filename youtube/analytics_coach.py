"""
Pit Crew's read on the Analytics page: one plain sentence about what happened, and three things to try next,
written by the AI from numbers Pit Crew has already worked out (YouTube, Instagram, each clip on both).

Rules that keep it honest:
- The AI only gets numbers (and titles); it never sees anything it could misread.
- Every number in its answer must be one of those numbers (or a small count like "3 clips"); a tip that quotes
  any other number is dropped, and if the headline does, the rule-based headline is used instead.
- With no AI key, or the AI busy, the same kind of read comes from rules(), so the page always has one.
- Never makes the page wait: the rule-based read shows at once and the AI's replaces it when ready.
- Cheap: ONE read per creator per day (key: user, channel, Instagram on/off, date), whatever range or platform the page
  shows. It's built from fixed numbers (Shorts all time, the last 28 days, Instagram's last 30 days, each clip since
  posted) and has a headline for both apps, one for YouTube only and one for Instagram only, so switching the range or
  the platform never asks the AI again. At most one AI call per creator per day (a failed one is retried after 10 min).
"""
import hashlib
import json
import re
import threading
import time
import traceback

from pipeline.ai import ai_json, has_key

CACHE_SECS = 24 * 3600
AI_TIMEOUT = 25  # seconds; the page waits for this, so never long (rules() answer otherwise)
_CACHE, _LOCK, _BUSY = {}, threading.Lock(), {}


def _pct(a, b):
    return round(100 * a / b) if b else None


def build_facts(range_label, content, dash, ig_acct, pairs):
    """The numbers the read is based on. dash = youtube.analytics.dashboard() output (or None), ig_acct =
    instagram.account_insights() output (or None), pairs = web.analytics_pairs.clip_pairs()["clips"]."""
    f = {"period": range_label, "videos_shown": content}
    if dash and dash.get("full") is not False:
        t = dash.get("totals") or {}
        traffic = {r["source"]: r["views"] for r in dash.get("traffic") or []}
        tv = sum(traffic.values()) or 0
        countries = dash.get("countries") or []
        cv = t.get("views") or 0
        f["youtube"] = {
            "views": t.get("views"), "engaged_views": t.get("engaged"), "watch_hours": t.get("watch_hours"),
            "avg_percent_viewed": t.get("avg_pct"), "avg_view_seconds": t.get("avg_secs"), "likes": t.get("likes"),
            "comments": t.get("comments"), "shares": t.get("shares"), "new_subscribers": t.get("subs"),
            "views_previous_period": (dash.get("previous") or {}).get("views"),
            "percent_from_shorts_feed": _pct(traffic.get("SHORTS", 0), tv), "percent_from_search": _pct(traffic.get("YT_SEARCH", 0), tv),
            "top_countries_percent": {c["code"]: _pct(c["views"], cv) for c in countries[:3]},
            "top_videos": [{"title": s.get("title", "")[:80], "views": s.get("views"), "percent_viewed": s.get("avg_pct"),
                            "seconds_long": round(s["secs"]) if s.get("secs") else None, "likes": s.get("likes"), "made_with_pit_crew": bool(s.get("clipline"))}
                           for s in (dash.get("shorts") or [])[:6] if s.get("views")],
        }
        daily = [d["views"] for d in dash.get("daily") or []]
        if len(daily) >= 4 and sum(daily):
            top2 = sorted(daily, reverse=True)[:2]
            f["youtube"]["percent_of_views_on_best_2_days"] = _pct(sum(top2), sum(daily))
    if ig_acct:
        t = ig_acct.get("totals") or {}
        rb = ig_acct.get("reach_by") or {}
        f["instagram"] = {"days": ig_acct.get("days"), "views": t.get("views"), "accounts_reached": t.get("reach"),
                          "likes": t.get("likes"), "comments": t.get("comments"), "shares": t.get("shares"),
                          "saves": t.get("saves"), "new_followers": (ig_acct.get("follows") or {}).get("FOLLOWER"),
                          "percent_reach_non_followers": _pct(rb.get("NON_FOLLOWER", 0), sum(rb.values()))}
    both = []
    for c in pairs or []:
        y, i = c.get("youtube") or {}, c.get("instagram") or {}
        if y.get("views") is None and i.get("views") is None:
            continue
        both.append({"clip": c["title"][:80], "seconds_long": round(c["length"]) if c.get("length") else None,
                     "youtube": {k: y.get(k) for k in ("views", "likes", "comments", "shares", "subs", "avg_pct")} if y else None,
                     "instagram": {k: i.get(k) for k in ("views", "likes", "comments", "shares", "saved", "follows")} if i else None})
    if both:
        f["pit_crew_clips_lifetime_totals"] = both[:8]
    return f


def daily_facts(dash_all, dash_28, ig_acct, pairs):
    """The numbers the daily read is based on: Shorts all time and the last 28 days, Instagram's last 30 days, and
    each Pit Crew clip since it was posted. Each part is labelled with its time span, so the AI can't mix them up."""
    f = {}
    a = build_facts("all time", "shorts", dash_all, None, pairs)
    if a.get("youtube"):
        f["youtube_shorts_all_time"] = a["youtube"]
    r = build_facts("last 28 days", "shorts", dash_28, None, [])
    if r.get("youtube"):
        f["youtube_shorts_last_28_days"] = {k: v for k, v in r["youtube"].items() if k != "top_videos"}
    i = build_facts("", "", None, ig_acct, [])
    if i.get("instagram"):
        f["instagram_reels_last_%s_days" % (ig_acct.get("days") or 30)] = i["instagram"]
    if a.get("pit_crew_clips_lifetime_totals"):
        f["pit_crew_clips_lifetime_totals"] = a["pit_crew_clips_lifetime_totals"]
    return f


def _yt(f):
    return f.get("youtube_shorts_all_time") or f.get("youtube") or {}


def _ig(f):
    return next((v for k, v in f.items() if k.startswith("instagram")), None) or {}


def _numbers(obj):
    """Every number in the facts, plus the forms an answer may write it in (rounded, 1 decimal, percent)."""
    out = set()

    def add(v):
        if isinstance(v, bool) or v is None:
            return
        if isinstance(v, (int, float)):
            out.update({round(v), round(v, 1)})
        elif isinstance(v, str):  # numbers inside titles ("700 Years of History") may be quoted too
            out.update(_quoted(v))
        elif isinstance(v, dict):
            for x in v.values():
                add(x)
        elif isinstance(v, list):
            for x in v:
                add(x)
    add(obj)
    return out


def _quoted(text):
    return [float(n.replace(",", "")) for n in re.findall(r"(?<![\w.])\d[\d,]*(?:\.\d+)?", text or "")]


def _honest(text, allowed):
    """True if every number in the text is in the facts (±1 for rounding) or a small count (0-10)."""
    for n in _quoted(text):
        if n <= 10 and n == int(n):
            continue
        if not any(abs(n - a) <= (1 if n >= 10 else 0.05) for a in allowed):
            return False
    return True


PROMPT = """You are Pit Crew's analytics coach for a video creator who posts the same clips as YouTube Shorts and
Instagram Reels. Below are their numbers as JSON; every key says its time span. Write, in plain friendly English a
15-year-old understands:

1. "headline": one or two sentences (max 45 words) on the single most useful thing these numbers show. If both apps
   have numbers, say how they differ.
2. "headline_youtube": the same, about YouTube only ("" if there are no YouTube numbers).
3. "headline_instagram": the same, about Instagram only ("" if there are no Instagram numbers).
4. "tips": 4 or 5 things to try next, each {"platform": "youtube" | "instagram" | "both", "title": max 7 words,
   "because": one sentence citing the number it comes from and its time span, "try": one concrete action, max 18
   words}. Give at least 2 per app that has numbers.

Rules:
- Use ONLY numbers that appear in the JSON (you may round them). Never invent a number, a cause you can't see in the
  data, or a benchmark ("most creators get...").
- Say which time span a number is from ("all time", "in the last 28 days", "since it was posted"). Never mix spans:
  "pit_crew_clips_lifetime_totals" are each clip's totals since it was posted.
- Each "because" must be a fact from the numbers that directly supports its "try". Don't link things the numbers
  don't link (which days views came on says nothing about a clip's first seconds).
- Write numbers with commas (1,449) and percentages as 53%.
- If there are fewer than 5 clips, say these are early hints.
- No jargon (no "CTR", "algorithm", "engagement rate"). No emoji. No markdown.
- Reply with JSON only: {"headline": "...", "headline_youtube": "...", "headline_instagram": "...", "tips": [...]}.

Numbers:
"""


def rules(f):
    """The read without AI: the biggest plain facts, worded by rules (same shape as the AI's)."""
    y, i, tips = _yt(f), _ig(f), []
    r28 = f.get("youtube_shorts_last_28_days") or {}
    vids = y.get("top_videos") or []
    hy = hi = ""
    if vids and y.get("views"):
        top = vids[0]
        hy = f"Your top Short, “{top['title']}”, brought {_pct(top['views'] or 0, y['views'])}% of all your Shorts views so far."
    if i.get("views"):
        hi = f"Your Instagram Reels were viewed {i['views']:,} times in the last {i.get('days')} days."
    head = hy or hi or "Not enough numbers yet. Once your clips have a few days of views, Pit Crew explains what's working."
    if y.get("percent_from_search") is not None:
        tips.append({"platform": "youtube", "title": "Make videos people search for",
                     "because": f"{y['percent_from_search']}% of your Shorts views so far came from YouTube search.",
                     "try": "Name the place, dish or event in the title and the first line."})
    if y.get("avg_percent_viewed"):
        tips.append({"platform": "youtube", "title": "Show it while you say it",
                     "because": f"People watch {round(y['avg_percent_viewed'])}% of each Short on average, all time.",
                     "try": "Put the place or dish on screen in the first 2 seconds, while you say the hook."})
    best2 = r28.get("percent_of_views_on_best_2_days")
    if best2 and best2 >= 60:
        tips.append({"platform": "both", "title": "Space your clips out",
                     "because": f"In the last 28 days, {best2}% of your views came on just 2 days.",
                     "try": "Post one clip every 2 days so each gets its own days."})
    if y.get("views") and y.get("new_subscribers") is not None and y["new_subscribers"] <= 0:
        tips.append({"platform": "youtube", "title": "Give viewers a reason to follow",
                     "because": f"{y['views']:,} Shorts views so far brought {y['new_subscribers']} new subscribers.",
                     "try": "End with where the full story is: your vlog on the channel."})
    if i.get("shares"):
        tips.append({"platform": "instagram", "title": "Make clips worth sending",
                     "because": f"Your Reels were shared {i['shares']:,} times in the last {i.get('days')} days.",
                     "try": "End with a question people want to answer or send to a friend."})
    if i.get("percent_reach_non_followers") is not None:
        tips.append({"platform": "instagram", "title": "Reach people who don't follow you",
                     "because": f"{i['percent_reach_non_followers']}% of the accounts your Reels reached don't follow you.",
                     "try": "Open with the most surprising second so new people stop scrolling."})
    return {"headline": head, "headline_youtube": hy, "headline_instagram": hi, "tips": _fill([], tips, f), "source": "rules"}


def _providers():
    """The AIs that may read a channel's YouTube numbers: Gemini only on a paid plan (pipeline/ai.py youtube_data_ok);
    none means the rule-based read."""
    from pipeline.ai import youtube_data_ok
    return [p for p in ("gemini", "openai") if has_key(p) and youtube_data_ok(p)]


MAX_KEPT = 2000  # reads kept in memory (oldest dropped); one per creator per day


def cached(key):
    """Today's read for this key, or None (the route checks this before fetching any numbers)."""
    with _LOCK:
        hit = _CACHE.get(key)
        return hit[1] if hit and time.time() < hit[0] else None


def read(key, facts):
    """Today's read: from the cache, else the rule-based read at once, marked pending, while the AI writes its read
    in the background (it can take a minute when Gemini is slow; the page asks again and swaps it in)."""
    hit = cached(key)
    if hit:
        return hit
    if not _providers():  # no AI may read these numbers (free Gemini): the rule-based read, at once
        return rules(facts)
    with _LOCK:
        if key not in _BUSY:  # two tabs loading at once ask the AI once
            _BUSY[key] = threading.Thread(target=_work, args=(key, facts), daemon=True)
            _BUSY[key].start()
    return {**rules(facts), "pending": True}


def _work(key, facts):
    try:
        out = _ask(facts) or rules(facts)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        out = rules(facts)
    with _LOCK:
        # kept until the day in the key is over (the key carries the date); rule-based: ask the AI again in 10 min
        _CACHE[key] = (time.time() + (CACHE_SECS if out["source"] == "ai" else 600), out)
        _BUSY.pop(key, None)
        if len(_CACHE) > MAX_KEPT:
            for k in sorted(_CACHE, key=lambda k: _CACHE[k][0])[:len(_CACHE) - MAX_KEPT]:
                _CACHE.pop(k, None)


def _same_point(tip, tips):
    """True if a rule-based tip repeats one already there: same title, or its "because" quotes the same figure
    (the AI's "search friendly names" and the rule's "videos people search for" both cite "48% from search")."""
    figs = {n for n in _quoted(tip["because"]) if n > 10}
    return any(tip["title"] == t["title"] or figs & set(_quoted(t["because"])) for t in tips)


def _fill(tips, extra, facts):
    """At least 2 tips for each app that has numbers (the page filters by app), topped up from the rule-based ones
    without repeating a point; at most 6."""
    for plat, has in (("youtube", _yt(facts)), ("instagram", _ig(facts))):
        if not has:
            continue
        for t in extra:
            if sum(x["platform"] in (plat, "both") for x in tips) >= 2:
                break
            if t["platform"] in (plat, "both") and not _same_point(t, tips):
                tips.append(t)
    if len(tips) < 3:
        tips += [t for t in extra if not _same_point(t, tips)][:3 - len(tips)]
    return tips[:6]


def _ask(facts):
    allowed = _numbers(facts)
    for provider in _providers():
        try:
            got = ai_json(PROMPT + json.dumps(facts, ensure_ascii=False, default=str), temperature=0.3,
                          provider=provider, timeout=AI_TIMEOUT, busy_waits=[])
        except Exception as e:  # noqa: BLE001  (busy, limit, no key...: try the next one, then rules)
            print(f"Analytics read with {provider} didn't work:", repr(e)[:200])
            continue
        if not isinstance(got, dict):
            continue
        rb = rules(facts)
        heads = {}
        for k in ("headline", "headline_youtube", "headline_instagram"):
            h = " ".join(str(got.get(k) or "").split())[:400]
            if h and not _honest(h, allowed):
                print(f"Analytics read: {k} used a number not in the data; using the rule-based one:", h)
                h = ""
            heads[k] = h or rb[k]
        tips = []
        for t in got.get("tips") or []:
            if not isinstance(t, dict):
                continue
            tip = {"platform": t.get("platform") if t.get("platform") in ("youtube", "instagram", "both") else "both",
                   "title": " ".join(str(t.get("title") or "").split())[:80],
                   "because": " ".join(str(t.get("because") or "").split())[:240],
                   "try": " ".join(str(t.get("try") or "").split())[:200]}
            if tip["title"] and tip["try"] and _honest(tip["because"] + " " + tip["try"], allowed):
                tips.append(tip)
            else:
                print("Analytics read: dropped a tip with a number not in the data:", tip)
        return {**heads, "tips": _fill(tips, rb["tips"], facts), "source": "ai"}
    return None
