"""
Connect Instagram: the sign-in window, Instagram's callback, the account line, sign-out.
"""
import html
import json
import traceback

from flask import g, jsonify, redirect, request, session

import instagram as ig

from web.google_redirect import instagram_redirect_uri
from web.server import app


@app.get("/api/instagram/signin")
def instagram_signin():
    popup = request.args.get("popup") == "1"
    try:
        url, session["instagram"] = ig.start_login(instagram_redirect_uri(), popup)
        return redirect(url)
    except ig.InstagramError as e:
        return instagram_done_page(False, str(e), popup)


@app.get("/api/instagram/callback")
def instagram_callback():
    pending = session.pop("instagram", None) or {}
    popup = bool(pending.get("popup"))
    try:
        a = ig.finish_login(request.args.to_dict(), pending, g.user["id"])
    except ig.InstagramError as e:
        return instagram_done_page(False, str(e), popup)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return instagram_done_page(False, "Something went wrong while connecting Instagram. Try again.", popup)
    ig.forget_insights(g.user["id"])
    msg = f"Connected @{a.get('username', '')}."
    if not a.get("can_post"):
        msg += (" This is a personal account, so Clipline can't post to it yet: in the Instagram app go to "
                "Settings › Account type and tools › Switch to professional account, then connect again.")
    return instagram_done_page(True, msg + (" You can close this window." if popup and a.get("can_post") else ""), popup)


def instagram_done_page(ok, msg, popup=False):
    payload = json.dumps({"clipline": "instagram", "ok": ok, "msg": msg}).replace("<", "\\u003c")
    return (f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Clipline · Instagram</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{{font:16px/1.5 system-ui,sans-serif;margin:0;min-height:100vh;display:grid;place-items:center;
background:#0e1018;color:#e8eaf2;padding:16px}}main{{max-width:440px;text-align:center}}a{{color:#8fb4ff}}</style>
</head><body><main><h1 style="font-size:1.3rem">{"Instagram connected" if ok else "Instagram not connected"}</h1>
<p>{html.escape(msg)}</p><p><a href="/">Back to Clipline</a></p></main>
<script>
var m={payload};
if({json.dumps(popup)}){{ try{{ window.opener && window.opener.postMessage(m, location.origin); }}catch(e){{}}
  if(m.ok && !/personal account/.test(m.msg)) setTimeout(function(){{ window.close(); }}, 900); }}
else if(m.ok) setTimeout(function(){{ location.replace("/"); }}, 1500);
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
