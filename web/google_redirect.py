"""
The address Google sends people back to after signing in (must match the OAuth client exactly).
"""
import os

from flask import request


# The page opens /api/youtube/signin in a small window. Google sends the creator back to the callback,
# which saves the sign-in, tells the page and closes the window.
def youtube_redirect_uri():
    # Must match a redirect address on the Google OAuth client exactly (see README step 5).
    return os.getenv("YOUTUBE_REDIRECT_URI") or request.host_url.rstrip("/") + "/api/youtube/callback"


def instagram_redirect_uri():
    # Must match a "Valid OAuth Redirect URI" on the Meta app exactly (see README step 6).
    return os.getenv("INSTAGRAM_REDIRECT_URI") or request.host_url.rstrip("/") + "/api/instagram/callback"
