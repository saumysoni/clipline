"""
Everything that talks to Instagram (Instagram API with Instagram Login). Each part has its own file;
this file only lets other code write ig.post_reel(...) etc. Inside instagram/, import from the part's file.
"""
from instagram.config import is_configured  # noqa: F401
from instagram.http import InstagramError  # noqa: F401
from instagram.connection import account, finish_login, sign_out, start_login, switch  # noqa: F401
from instagram.publish import caption_for, post_reel  # noqa: F401
from instagram.insights import dashboard, forget as forget_insights, snapshot_reels  # noqa: F401
