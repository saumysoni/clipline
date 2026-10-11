"""
Analytics: Pit Crew's read (headline + 3 things to try) for the Overview, from youtube/analytics_coach.py. The page
asks for it automatically after the numbers load; it's cached per set of numbers, so the AI isn't asked on every load.
"""
import traceback

from flask import g, jsonify, request

import instagram as ig
import youtube as yt
from instagram.account_insights import account_insights
from youtube.analytics_coach import build_facts, read, rules

from web.analytics_more import _clip_ids, period_args
from web.analytics_pairs import clip_pairs
from web.server import app


@app.get("/api/analytics/coach")
def analytics_coach():
    uid = g.user["id"]
    start, end, content, days = period_args()
    label = (f"last {days} days" if days else "all time") if days is not None else f"{start} to {end}"
    dash = acct = None
    try:
        if yt.account(uid)["signed_in"]:
            dash = (yt.analytics_dashboard(uid, days, _clip_ids(uid), content=content) if days is not None else
                    yt.analytics_dashboard(uid, 0, _clip_ids(uid), content=content, start=start, end=end))
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    try:
        acct = account_insights(uid, 7 if days and days <= 7 else 30)
    except ig.InstagramError:
        acct = None
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    try:
        pairs = clip_pairs(uid)["clips"]
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        pairs = []
    plat = request.args.get("plat", "")
    if plat == "youtube":  # the page shows one platform: the read is about that one
        acct, pairs = None, [{**c, "instagram": None} for c in pairs]
    elif plat == "instagram":
        dash, pairs = None, [{**c, "youtube": None} for c in pairs]
    facts = build_facts(label, content, dash, acct, pairs)
    if not facts.get("youtube") and not facts.get("instagram"):
        return jsonify(headline="", tips=[], source="none")
    try:
        out = read(facts)
        if plat in ("youtube", "instagram"):  # never a tip about the platform that isn't shown
            keep = lambda t: t["platform"] in (plat, "both")
            tips = [t for t in out["tips"] if keep(t)]
            tips += [t for t in rules(facts)["tips"] if keep(t) and t["title"] not in {x["title"] for x in tips}]
            out = {**out, "tips": tips[:3]}
        return jsonify(out)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return jsonify(headline="", tips=[], source="none")
