"""
Pit Crew's read on the Analytics page: one plain sentence about what happened, and three things to try next,
written by the AI from numbers Pit Crew has already worked out (YouTube, Instagram, each clip on both).

Rules that keep it honest:
- The AI only gets numbers (and titles); it never sees anything it could misread.
- Every number in its answer must be one of those numbers (or a small count like "3 clips"); a tip that quotes
  any other number is dropped, and if the headline does, the rule-based headline is used instead.
- With no AI key, or the AI busy, the same kind of read comes from rules(), so the page always has one.
- Never makes the page wait: the rule-based read shows at once and the AI's replaces it when ready.
- Automatic, but cheap: the answer is kept for a day per set of numbers (a fingerprint of the facts), so the AI is
  asked again only when the numbers change (YouTube updates about once a day).
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
Instagram Reels. Below are their numbers as JSON. Write, in plain friendly English a 15-year-old understands:

1. "headline": one or two sentences (max 45 words) on the single most useful thing these numbers show. If both
   platforms have numbers, say how they differ.
2. "tips": exactly 3 things to try next, each {"platform": "youtube" | "instagram" | "both", "title": max 7 words,
   "because": one sentence citing the number it comes from, "try": one concrete action, max 18 words}.

Rules:
- Use ONLY numbers that appear in the JSON (you may round them). Never invent a number, a cause you can't see in the
  data, or a benchmark ("most creators get...").
- "period" is the time span the page shows. Numbers under "youtube" and "instagram" are for that period only.
  Numbers under "pit_crew_clips_lifetime_totals" are each clip's totals since it was posted, NOT this period: never
  call them this period's numbers or use them to say which clip won this period.
- Each "because" must be a fact from the numbers that directly supports its "try". Don't link things the numbers
  don't link (which days views came on says nothing about a clip's first seconds).
- Write numbers with commas (1,449) and percentages as 53%.
- If there are fewer than 5 clips, say these are early hints.
- No jargon (no "CTR", "algorithm", "engagement rate"). No emoji. No markdown.
- Reply with JSON only: {"headline": "...", "tips": [...]}.

Numbers:
"""


def rules(f):
    """The read without AI: the biggest plain facts, worded by rules."""
    y, i, tips = f.get("youtube") or {}, f.get("instagram") or {}, []
    vids = y.get("top_videos") or []
    head = ""
    if vids and y.get("views"):
        top = vids[0]
        share = _pct(top["views"] or 0, y["views"])
        head = f"Your top video, “{top['title']}”, brought {share}% of your YouTube views in this period."
    elif i.get("views"):
        head = f"Your Instagram Reels were viewed {i['views']:,} times in the last {i.get('days')} days."
    else:
        head = "Not enough numbers yet. Once your clips have a few days of views, Pit Crew explains what's working."
    if y.get("percent_from_search") is not None:
        tips.append({"platform": "youtube", "title": "Make videos people search for",
                     "because": f"{y['percent_from_search']}% of your YouTube views came from search.",
                     "try": "Name the place, dish or event in the title and the first line."})
    if y.get("percent_of_views_on_best_2_days") and y["percent_of_views_on_best_2_days"] >= 60:
        tips.append({"platform": "both", "title": "Space your clips out",
                     "because": f"{y['percent_of_views_on_best_2_days']}% of your views came on just 2 days.",
                     "try": "Post one clip every 2 days so each gets its own days."})
    if y.get("views") and y.get("new_subscribers") is not None and y["new_subscribers"] <= 0:
        tips.append({"platform": "youtube", "title": "Give viewers a reason to follow",
                     "because": f"{y['views']:,} views brought {y['new_subscribers']} new subscribers.",
                     "try": "End with where the full story is: your vlog on the channel."})
    if i.get("shares") and len(tips) < 3:
        tips.append({"platform": "instagram", "title": "Make clips worth sending",
                     "because": f"Your Reels were shared {i['shares']:,} times.",
                     "try": "End with a question people want to answer or send to a friend."})
    return {"headline": head, "tips": tips[:3], "source": "rules"}


def _providers():
    return [p for p in ("gemini", "openai") if has_key(p)]


MAX_KEPT = 500  # answers kept in memory (oldest dropped)


def read(facts):
    """The headline + 3 tips for these facts. From the cache when it has them; otherwise the rule-based read now,
    marked pending, while the AI writes its read in the background (it can take a minute when Gemini is slow;
    the page asks again and swaps it in)."""
    key = hashlib.sha256(json.dumps(facts, sort_keys=True, default=str).encode()).hexdigest()
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and time.time() - hit[0] < CACHE_SECS:
            return hit[1]
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
        _CACHE[key] = (time.time() if out["source"] == "ai" else time.time() - CACHE_SECS + 600, out)  # rules: retry AI in 10 min
        _BUSY.pop(key, None)
        if len(_CACHE) > MAX_KEPT:
            for k in sorted(_CACHE, key=lambda k: _CACHE[k][0])[:len(_CACHE) - MAX_KEPT]:
                _CACHE.pop(k, None)


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
        head = " ".join(str(got.get("headline") or "").split())[:400]
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
        if not head or not _honest(head, allowed):
            print("Analytics read: headline used a number not in the data; using the rule-based one:", head)
            head = rules(facts)["headline"]
        if len(tips) < 3:
            tips += [t for t in rules(facts)["tips"] if t["title"] not in {x["title"] for x in tips}][:3 - len(tips)]
        return {"headline": head, "tips": tips[:3], "source": "ai"}
    return None
