"""
Analytics: Pit Crew's read (a headline for both apps, one per app, and things to try) for the Overview, from
youtube/analytics_coach.py. ONE read per creator per day, whatever range or platform the page shows: the AI is asked
at most once a day per creator (key: user, YouTube channel, Instagram on/off, date). The page picks the headline and
tips for the platform it shows.
"""
import traceback
from datetime import date

from flask import g, jsonify

import instagram as ig
import youtube as yt
from instagram.account_insights import account_insights
from youtube.analytics_coach import cached, daily_facts, read
from youtube.analytics_more import _chan

from web.analytics_more import _clip_ids
from web.analytics_pairs import clip_pairs
from web.server import app


@app.get("/api/analytics/coach")
def analytics_coach():
    uid = g.user["id"]
    signed = {}
    try:
        signed["yt"] = bool(yt.account(uid)["signed_in"])
    except Exception:  # noqa: BLE001
        signed["yt"] = False
    try:
        st = ig.account(uid)
        signed["ig"] = bool(st.get("signed_in") and st.get("can_post"))
    except Exception:  # noqa: BLE001
        signed["ig"] = False
    key = (uid, _chan(uid) if signed["yt"] else "", signed["ig"], date.today().isoformat())
    hit = cached(key)
    if hit:
        return jsonify(hit)
    dash_all = dash_28 = acct = None
    if signed["yt"]:
        try:
            ids = _clip_ids(uid)
            dash_all = yt.analytics_dashboard(uid, 0, ids, content="shorts")
            dash_28 = yt.analytics_dashboard(uid, 28, ids, content="shorts")
        except Exception:  # noqa: BLE001
            traceback.print_exc()
    if signed["ig"]:
        try:
            acct = account_insights(uid, 30)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
    try:
        pairs = clip_pairs(uid)["clips"]
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        pairs = []
    facts = daily_facts(dash_all, dash_28, acct, pairs)
    if not facts:
        return jsonify(headline="", tips=[], source="none")
    try:
        return jsonify(read(key, facts))
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return jsonify(headline="", tips=[], source="none")
