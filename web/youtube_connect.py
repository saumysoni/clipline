"""
Connect YouTube: the sign-in window, Google's callback (which also finishes Google login), sign-out.
"""
import html
import json
import re
import traceback

from flask import g, jsonify, redirect, request, session

import youtube as yt

from web.accounts import google_user, login_problem_page, start_session
from web.google_redirect import youtube_redirect_uri
from web.server import app


@app.get("/api/youtube/signin")
def youtube_signin():
    """Connect YouTube (opened in a small window from a signed-in page)."""
    nxt = request.args.get("next", "")
    nxt = nxt if re.fullmatch(r"[0-9a-f]{10}", nxt) else ""
    popup = request.args.get("popup") == "1"
    try:
        url, session["google"] = yt.start_google("youtube", youtube_redirect_uri(), nxt, popup)
        return redirect(url)
    except RuntimeError as e:
        return youtube_done_page(False, str(e), nxt, popup)


@app.get("/api/youtube/callback")
def youtube_callback():
    """Google sends both kinds of sign-in back here (the one address registered on the OAuth client)."""
    pending = session.pop("google", None) or {}
    if pending.get("purpose") == "login":
        try:
            user = google_user(yt.finish_login(request.args.to_dict(), pending))
        except RuntimeError as e:
            return login_problem_page(str(e))
        except Exception:
            traceback.print_exc()
            return login_problem_page("Something went wrong while signing in. Try again.")
        start_session(user)
        return redirect("/")
    nxt, popup = pending.get("next", ""), bool(pending.get("popup"))
    if not g.user:
        return youtube_done_page(False, "Sign in to Clipline first, then connect YouTube.", nxt, popup)
    try:
        channel = yt.finish_youtube(request.args.to_dict(), pending, g.user["id"])
        return youtube_done_page(True, f"Connected {channel['title']}."
                                       + (" You can close this window." if popup else ""), nxt, popup)
    except RuntimeError as e:
        return youtube_done_page(False, str(e), nxt, popup)
    except Exception:
        traceback.print_exc()
        return youtube_done_page(False, "Something went wrong while connecting YouTube. Try again.", nxt, popup)


def youtube_done_page(ok, msg, nxt="", popup=False):
    # In the small sign-in window: tell the page (if the browser kept the link to it) and close.
    # Opened in the same tab (popups blocked): go back to the job's page.
    back = "/" + ("#" + nxt if nxt else "")
    payload = json.dumps({"clipline": "youtube", "ok": ok, "msg": msg}).replace("<", "\\u003c")
    return (f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Clipline · YouTube</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{{font:16px/1.5 system-ui,sans-serif;margin:0;min-height:100vh;display:grid;place-items:center;
background:#0e1018;color:#e8eaf2;padding:16px}}main{{max-width:420px;text-align:center}}
a{{color:#8fb4ff}}</style></head><body><main><h1 style="font-size:1.3rem">
{"YouTube connected" if ok else "YouTube not connected"}</h1><p>{html.escape(msg)}</p>
<p><a href="{back}">Back to Clipline</a></p></main>
<script>
var m={payload};
if({json.dumps(popup)}){{ try{{ window.opener && window.opener.postMessage(m, location.origin); }}catch(e){{}}
  if(m.ok) setTimeout(function(){{ window.close(); }}, 800); }}
else if(m.ok) setTimeout(function(){{ location.replace({json.dumps(back)}); }}, 900);
</script></body></html>""", 200 if ok else 400)


@app.post("/api/youtube/signout")
def youtube_signout():
    yt.sign_out(g.user["id"])
    return jsonify(ok=True)


@app.get("/api/youtube/me")
def youtube_me():
    return jsonify(yt.account(g.user["id"]))
