"""
Instagram settings: the Meta app (INSTAGRAM_APP_ID / INSTAGRAM_APP_SECRET in .env), the API version and
the permissions Pit Crew asks for. Setup: README step 6.

Pit Crew uses the "Instagram API with Instagram Login": the creator signs in with Instagram itself (no
Facebook Page needed). Only professional accounts (Business or Creator) can be posted to by an app.
"""
import os


API_VERSION = os.getenv("INSTAGRAM_API_VERSION", "v24.0")
GRAPH = "https://graph.instagram.com"
AUTHORIZE_URL = "https://www.instagram.com/oauth/authorize"
TOKEN_URL = "https://api.instagram.com/oauth/access_token"
NET_TIMEOUT = 30


# basic: who the account is; content_publish: post Reels; manage_insights: views, reach, likes... for Analytics
SCOPES = ["instagram_business_basic", "instagram_business_content_publish", "instagram_business_manage_insights"]


def app_id():
    return os.getenv("INSTAGRAM_APP_ID", "").strip()


def app_secret():
    return os.getenv("INSTAGRAM_APP_SECRET", "").strip()


def is_configured():
    return bool(app_id() and app_secret())
