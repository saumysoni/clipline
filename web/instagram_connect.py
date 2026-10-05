"""
Connect Instagram: the sign-in window, Instagram's callback, the account line, sign-out.

The waiting sign-in is kept here on the server (keyed by its one-time state), not in the browser's cookie, so
Instagram may send the creator back to a different address than the one Pit Crew is open at. Meta may only
accept https redirect addresses; then INSTAGRAM_REDIRECT_URI points at an https tunnel to this computer while
the creator keeps using http://localhost:8000 (README step 6). Kept in memory: one Pit Crew process.
"""
import html
import json
import threading
import time
import traceback

from flask import g, jsonify, redirect, request

import instagram as ig

from web.google_redirect import instagram_redirect_uri
from web.server import app


PENDING = {}  # state -> {"uid", "redirect_uri", "popup", "at", "state"}
_PLOCK = threading.Lock()
PENDING_FOR = 15 * 60  # seconds a sign-in window may stay open


def _take_pending(state):
    with _PLOCK:
        now = time.time()
        for k in [k for k, v in PENDING.items() if now - v["at"] > PENDING_FOR]:
            PENDING.pop(k, None)
        return PENDING.pop(state, None) if state else None


@app.get("/api/instagram/signin")
def instagram_signin():
    popup = request.args.get("popup") == "1"
    try:
        url, pending = ig.start_login(instagram_redirect_uri(), popup)
    except ig.InstagramError as e:
        return instagram_done_page(False, str(e), popup)
    with _PLOCK:
        PENDING[pending["state"]] = {**pending, "uid": g.user["id"], "at": time.time()}
    return redirect(url)


@app.get("/api/instagram/callback")
def instagram_callback():
    """Public (see PUBLIC in web/accounts.py): the one-time state says whose sign-in this is."""
    pending = _take_pending(request.args.get("state", ""))
    popup = bool((pending or {}).get("popup"))
    if not pending:
        return instagram_done_page(False, "This sign-in window is out of date. Close it and click Connect Instagram again.",
                                   popup)
    uid = pending["uid"]
    try:
        a = ig.finish_login(request.args.to_dict(), pending, uid)
    except ig.InstagramError as e:
        return instagram_done_page(False, str(e), popup)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return instagram_done_page(False, "Something went wrong while connecting Instagram. Try again.", popup)
    ig.forget_insights(uid)
    msg = f"Connected @{a.get('username', '')}."
    if not a.get("can_post"):
        msg += (" This is a personal account, so Pit Crew can't post to it yet: in the Instagram app go to "
                "Settings › Account type and tools › Switch to professional account, then connect again.")
    return instagram_done_page(True, msg + (" You can close this window." if popup and a.get("can_post") else ""), popup)


def instagram_done_page(ok, msg, popup=False):
    payload = json.dumps({"clipline": "instagram", "ok": ok, "msg": msg}).replace("<", "\\u003c")
    return (f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Pit Crew · Instagram</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{{font:16px/1.5 system-ui,sans-serif;margin:0;min-height:100vh;display:grid;place-items:center;
background:#0e1018;color:#e8eaf2;padding:16px}}main{{max-width:440px;text-align:center}}a{{color:#8fb4ff}}</style>
</head><body><main><h1 style="font-size:1.3rem">{"Instagram connected" if ok else "Instagram not connected"}</h1>
<p>{html.escape(msg)}</p><p><a href="/">Back to Pit Crew</a></p></main>
<script>
var m={payload};
if({json.dumps(popup)}){{ try{{ window.opener && window.opener.postMessage(m, location.origin); }}catch(e){{}}
  if(m.ok && !/personal account/.test(m.msg)) setTimeout(function(){{ window.close(); }}, 900); }}
else if(m.ok && location.hostname==="localhost") setTimeout(function(){{ location.replace("/"); }}, 1500);
</script></body></html>""", 200 if ok else 400)


@app.get("/api/instagram/me")
def instagram_me():
    try:
        return jsonify(ig.account(g.user["id"]))
    except ig.InstagramError as e:
        return jsonify(configured=True, signed_in=True, offline=True, error=str(e))


@app.post("/api/instagram/signout")
def instagram_signout():
    ig.sign_out(g.user["id"])
    ig.forget_insights(g.user["id"])
    return jsonify(ok=True)
