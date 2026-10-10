"""
The Flask app object and its settings (sign-in cookie, upload size). Every web/*.py file adds its
routes to this one app; app.py imports them all.
"""
import logging
import os

from flask import Flask

from accounts import db
from settings import ROOT

app = Flask(__name__, static_folder=str(ROOT / "static"), static_url_path="/static")


class _HideStatusPolls(logging.Filter):
    """The page checks progress every second; don't print a line for each check."""
    def filter(self, record):
        return "/api/status/" not in record.getMessage()


logging.getLogger("werkzeug").addFilter(_HideStatusPolls())

# Behind a proxy or load balancer (the cloud), the visitor's address and https come in X-Forwarded-* headers. TRUST_PROXY
# = how many proxies are in front (usually 1); without it every visitor looks like the proxy, so the sign-in and sign-up
# limits would lock everyone out together. Never set it when nothing is in front: anyone could fake the headers.
if int(os.getenv("TRUST_PROXY", "0") or 0) > 0:
    from werkzeug.middleware.proxy_fix import ProxyFix
    n = int(os.environ["TRUST_PROXY"])
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=n, x_proto=n, x_host=n)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024  # videos come in 8 MB pieces (web/video_upload.py)

# Accounts: a signed session cookie holds the user's id. SESSION_COOKIE_SECURE=1 on an https server.
db.init()
app.secret_key = db.secret_key()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "") in ("1", "true", "yes"),
    PERMANENT_SESSION_LIFETIME=30 * 24 * 3600,
    SESSION_REFRESH_EACH_REQUEST=False,  # the sign-in window and the page share one cookie; don't overwrite it
)
