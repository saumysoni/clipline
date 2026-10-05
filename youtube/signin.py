"""
Google sign-in, for both purposes sharing one callback: "login" (sign in to Pit Crew with Google)
and "youtube" (connect a YouTube channel). Never go back to InstalledAppFlow.run_local_server().
"""
import os
import secrets
import urllib.request

from youtube.config import CONNECT_SCOPES, LOGIN_SCOPES, NET_TIMEOUT, YOUTUBE_SCOPE, client_config, client_id
from youtube.connection import _lookup_channel, _quick_request, save_connection


def _allow_http(redirect_uri):
    # oauthlib refuses plain http; that's fine (and needed) only for this computer's own address.
    host = urllib.parse.urlparse(redirect_uri).hostname or ""
    if host in ("localhost", "127.0.0.1", "::1"):
        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    # Google may grant more or fewer scopes than asked; Pit Crew checks them itself.
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"


def start_google(purpose, redirect_uri, next_id="", popup=False):
    """(Google's sign-in address, the waiting sign-in to keep in the creator's session).
    purpose is "login" (Pit Crew account) or "youtube" (connect a channel)."""
    from google_auth_oauthlib.flow import Flow

    if not client_config():
        raise RuntimeError("Google sign-in isn't set up yet: Pit Crew has no Google client. "
                           "Follow README step 5, then try again.")
    _allow_http(redirect_uri)
    scopes = LOGIN_SCOPES if purpose == "login" else CONNECT_SCOPES
    flow = Flow.from_client_config(client_config(), scopes, redirect_uri=redirect_uri)
    extra = ({"prompt": "select_account"} if purpose == "login"
             else {"access_type": "offline", "prompt": "consent select_account"})
    url, state = flow.authorization_url(**extra)
    return url, {"state": state, "verifier": flow.code_verifier, "redirect_uri": redirect_uri,
                 "purpose": purpose, "next": next_id, "popup": popup}


def _exchange(args, pending, scopes):
    """Swap Google's one-time code for tokens. Raises RuntimeError in plain words."""
    from google_auth_oauthlib.flow import Flow

    if args.get("error"):
        if args["error"] == "access_denied":
            raise RuntimeError("Sign-in was cancelled. Try again when you're ready.")
        raise RuntimeError(f"Google didn't finish the sign-in ({args['error']}). Try again.")
    if not pending or not args.get("code") or not secrets.compare_digest(
            str(args.get("state", "")), str(pending.get("state", ""))):
        raise RuntimeError("This sign-in page is out of date. Close it and try again.")
    _allow_http(pending["redirect_uri"])
    flow = Flow.from_client_config(client_config(), scopes, redirect_uri=pending["redirect_uri"],
                                         code_verifier=pending["verifier"], autogenerate_code_verifier=False)
    try:
        token = flow.fetch_token(code=args["code"], timeout=NET_TIMEOUT)
    except Exception as e:
        print("Google sign-in failed:", repr(e))
        raise RuntimeError("Google didn't accept the sign-in. Try again.") from e
    return flow, token


def finish_login(args, pending):
    """Google's reply to Sign in with Google -> {"sub", "email", "email_verified", "name"}."""
    from google.oauth2 import id_token

    _, token = _exchange(args, pending, LOGIN_SCOPES)
    try:
        info = id_token.verify_oauth2_token(token.get("id_token"), _quick_request(), client_id(),
                                              clock_skew_in_seconds=10)  # computer clocks drift a little
    except Exception as e:
        print("Google ID token check failed:", repr(e))
        raise RuntimeError("Google's sign-in reply couldn't be checked. Try again.") from e
    if not info.get("email"):
        raise RuntimeError("Google didn't share an email address for this account, so Pit Crew can't sign you in.")
    return {"sub": info["sub"], "email": info["email"].lower(), "email_verified": bool(info.get("email_verified")),
            "name": info.get("name", "")}


def finish_youtube(args, pending, user_id):
    """Google's reply to Connect YouTube: save the connection for this user and return their channel
    ({"id", "title", "thumb"}). Raises RuntimeError with a plain message."""
    flow, token = _exchange(args, pending, CONNECT_SCOPES)
    granted = token.get("scope") or []
    granted = set(granted.split() if isinstance(granted, str) else granted)
    if YOUTUBE_SCOPE not in granted:
        raise RuntimeError("Pit Crew needs permission to manage your YouTube videos, so it can upload, schedule "
                           "and update your Shorts. Connect again and leave that box ticked.")
    creds = flow.credentials
    if not creds.refresh_token:
        raise RuntimeError("Google didn't give Pit Crew a lasting connection. Open "
                           "https://myaccount.google.com/permissions, remove Pit Crew, then connect again.")
    try:
        channel = _lookup_channel(creds.token)
    except urllib.error.HTTPError as e:
        print("YouTube channel lookup failed:", e.code, e.read()[:300])
        raise RuntimeError("YouTube didn't answer Pit Crew. In Google Cloud, check that YouTube Data API v3 is "
                           "enabled for this project (README step 5.2), then connect again.") from e
    except OSError as e:
        raise RuntimeError("Couldn't reach YouTube. Check your internet connection and connect again.") from e
    if not channel:
        raise RuntimeError("This Google account has no YouTube channel. Create one at youtube.com, or connect "
                           "with the account that owns your channel.")
    save_connection(user_id, creds, channel)
    return channel
