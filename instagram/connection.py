"""
Each creator's Instagram connections: the sign-in window, swapping Instagram's code for a 60-day token,
keeping it fresh, the account's name and type, switching, signing out.

A creator can connect several Instagram accounts; one is active (where new Reels are planned). Every function
takes ig_id=None (the active account) or an Instagram user id. A planned Reel keeps the ig_id it was planned
for, so switching never sends it to another account.
"""
import secrets
import time
import urllib.parse

from accounts import db

from instagram.config import API_VERSION, AUTHORIZE_URL, GRAPH, SCOPES, TOKEN_URL, app_id, app_secret, is_configured
from instagram.http import InstagramError, call


REFRESH_BEFORE = 10 * 24 * 3600  # refresh the 60-day token when fewer than 10 days are left
PROFESSIONAL = ("BUSINESS", "MEDIA_CREATOR", "CREATOR")


def start_login(redirect_uri, popup=False, add=False):
    """(Instagram's sign-in address, the waiting sign-in to keep in the creator's session).
    add: connecting another account, so Instagram asks who to log in as (force_reauth) instead of reusing the
    account the browser is already logged in to."""
    if not is_configured():
        raise InstagramError("Instagram isn't set up yet: Pit Crew has no Meta app. Follow README step 6, then try again.")
    state = secrets.token_urlsafe(24)
    q = urllib.parse.urlencode({"client_id": app_id(), "redirect_uri": redirect_uri, "response_type": "code",
                                "scope": ",".join(SCOPES), "state": state, **({"force_reauth": "true"} if add else {})})
    return f"{AUTHORIZE_URL}?{q}", {"state": state, "redirect_uri": redirect_uri, "popup": popup}


def _profile(token):
    return call("GET", f"{GRAPH}/{API_VERSION}/me",
                {"fields": "user_id,username,account_type,profile_picture_url,name", "access_token": token})


def finish_login(args, pending, user_id):
    """Instagram's reply to Connect Instagram: save the connection (now the active one), return account(user_id)."""
    if args.get("error"):
        if args.get("error_reason") == "user_denied" or args["error"] == "access_denied":
            raise InstagramError("Connecting was cancelled. Try again when you're ready.")
        raise InstagramError(f"Instagram didn't finish connecting ({args.get('error_description') or args['error']}).")
    code = (args.get("code") or "").split("#")[0]
    if not pending or not code or not secrets.compare_digest(str(args.get("state", "")), str(pending.get("state", ""))):
        raise InstagramError("This sign-in page is out of date. Close it and try again.")
    short = call("POST", TOKEN_URL, data={"client_id": app_id(), "client_secret": app_secret(),
                                          "grant_type": "authorization_code",
                                          "redirect_uri": pending["redirect_uri"], "code": code})
    if isinstance(short.get("data"), list) and short["data"]:  # older answer shape
        short = short["data"][0]
    granted = short.get("permissions") or []
    granted = set(granted.split(",") if isinstance(granted, str) else granted)
    if granted and "instagram_business_content_publish" not in granted:
        raise InstagramError("Pit Crew needs permission to publish Reels. Connect again and leave every box ticked.")
    long = call("GET", f"{GRAPH}/access_token", {"grant_type": "ig_exchange_token", "client_secret": app_secret(),
                                                 "access_token": short["access_token"]})
    token = long["access_token"]
    me = _profile(token)
    info = {"token": token, "expires_at": int(time.time()) + int(long.get("expires_in") or 5184000),
            "ig_id": str(me.get("user_id") or me.get("id") or short.get("user_id")),
            "username": me.get("username", ""), "name": me.get("name", ""),
            "account_type": (me.get("account_type") or "").upper(), "picture": me.get("profile_picture_url", ""),
            "insights": "instagram_business_manage_insights" in granted or not granted}
    db.save_connection(user_id, "instagram", info["ig_id"], info)
    return account(user_id)


def load(user_id, ig_id=None):
    """A saved connection (ig_id None: the active one), refreshed when close to expiring, or None."""
    row = db.connection(user_id, "instagram", ig_id)
    if not row:
        return None
    info, now = row["token"], time.time()
    if info.get("expires_at", 0) < now:
        db.drop_connection(row["id"])
        return None
    if info["expires_at"] - now < REFRESH_BEFORE:
        try:
            r = call("GET", f"{GRAPH}/refresh_access_token", {"grant_type": "ig_refresh_token",
                                                              "access_token": info["token"]})
            info.update(token=r["access_token"], expires_at=int(now) + int(r.get("expires_in") or 5184000))
            db.update_connection(row["id"], token=info)
        except InstagramError as e:
            if e.expired:
                db.drop_connection(row["id"])
                return None
            print("Instagram token refresh failed (will retry):", e)
    return info


def is_professional(info):
    return (info or {}).get("account_type", "") in PROFESSIONAL


def _summary(info, active):
    return {"ig_id": info.get("ig_id", ""), "username": info.get("username", ""), "name": info.get("name", ""),
            "picture": info.get("picture", ""), "can_post": is_professional(info), "active": active}


def account(user_id):
    """What the page shows: configured, connected, the active account and whether Pit Crew can post to it, and
    "accounts" (every connected account, each with "active")."""
    if not is_configured():
        return {"configured": False, "signed_in": False, "accounts": []}
    accounts = [_summary(r["token"], r["active"]) for r in db.connections(user_id, "instagram")]
    info = load(user_id)
    if not info:
        return {"configured": True, "signed_in": False, "accounts": accounts}
    return {"configured": True, "signed_in": True, "ig_id": info.get("ig_id", ""), "username": info.get("username", ""),
            "name": info.get("name", ""), "picture": info.get("picture", ""),
            "account_type": info.get("account_type", ""), "can_post": is_professional(info),
            "days_left": max(0, int((info["expires_at"] - time.time()) // 86400)), "accounts": accounts}


def switch(user_id, ig_id):
    """Make a connected account the active one. False if it isn't connected."""
    return db.set_active(user_id, "instagram", ig_id)


def sign_out(user_id, ig_id=None):
    """Disconnect an account (None: the active one)."""
    row = db.connection(user_id, "instagram", ig_id)
    if row:
        db.drop_connection(row["id"])
