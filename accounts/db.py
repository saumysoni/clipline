"""
Accounts database (SQLite): who can sign in, and each person's YouTube and Instagram connections.

SQLite from Python's standard library, in data/clipline.db (DATABASE_PATH). One row per user;
the YouTube token is stored per user so every creator posts to their own channel.
"""
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path

from settings import ROOT


DB_PATH = Path(os.getenv("DATABASE_PATH") or ROOT / "data" / "clipline.db")


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL DEFAULT '',
    password_hash TEXT,
    google_sub TEXT UNIQUE,
    email_verified INTEGER NOT NULL DEFAULT 0,
    session_version INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS youtube_tokens (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    token_json TEXT NOT NULL,
    channel_json TEXT
);
CREATE TABLE IF NOT EXISTS instagram_tokens (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    token_json TEXT NOT NULL
);
"""


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def init():
    with connect() as con:
        con.executescript(SCHEMA)


def secret_key():
    """SECRET_KEY from .env, else one made once and kept in data/secret_key (so restarts keep people signed in)."""
    if os.getenv("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    path = DB_PATH.parent / "secret_key"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_hex(32))
        os.chmod(path, 0o600)
    return path.read_text().strip()


def _user(row):
    return dict(row) if row else None


def user_by_id(user_id):
    with connect() as con:
        return _user(con.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())


def user_by_email(email):
    with connect() as con:
        return _user(con.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone())


def user_by_google(sub):
    with connect() as con:
        return _user(con.execute("SELECT * FROM users WHERE google_sub = ?", (sub,)).fetchone())


def count_users():
    with connect() as con:
        return con.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def create_user(email, name="", password_hash=None, google_sub=None, email_verified=False):
    """The new user's id. Raises sqlite3.IntegrityError if the email (or Google account) is taken."""
    with connect() as con:
        cur = con.execute(
            "INSERT INTO users (email, name, password_hash, google_sub, email_verified, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (email.strip().lower(), name.strip()[:100], password_hash, google_sub, int(email_verified), time.time()))
        return cur.lastrowid


def link_google(user_id, sub, name, clear_password):
    """Attach a Google account to an existing user. clear_password: Google proved who owns this email, so a
    password someone set before (never checked) is removed and every old session ends."""
    with connect() as con:
        con.execute("UPDATE users SET google_sub = ?, email_verified = 1, "
                    "name = CASE WHEN name = '' THEN ? ELSE name END WHERE id = ?", (sub, name[:100], user_id))
        if clear_password:
            con.execute("UPDATE users SET password_hash = NULL, session_version = session_version + 1 "
                        "WHERE id = ?", (user_id,))


def youtube_token(user_id):
    with connect() as con:
        row = con.execute("SELECT token_json FROM youtube_tokens WHERE user_id = ?", (user_id,)).fetchone()
    return json.loads(row["token_json"]) if row else None


def save_youtube_token(user_id, token_json):
    with connect() as con:
        con.execute("INSERT INTO youtube_tokens (user_id, token_json) VALUES (?, ?) "
                    "ON CONFLICT(user_id) DO UPDATE SET token_json = excluded.token_json", (user_id, token_json))


def drop_youtube_token(user_id):
    with connect() as con:
        con.execute("DELETE FROM youtube_tokens WHERE user_id = ?", (user_id,))


def instagram_token(user_id):
    """This user's Instagram connection: {"token", "expires_at", "ig_id", "username", ...}, or None."""
    with connect() as con:
        row = con.execute("SELECT token_json FROM instagram_tokens WHERE user_id = ?", (user_id,)).fetchone()
    return json.loads(row["token_json"]) if row else None


def save_instagram_token(user_id, info):
    with connect() as con:
        con.execute("INSERT INTO instagram_tokens (user_id, token_json) VALUES (?, ?) "
                    "ON CONFLICT(user_id) DO UPDATE SET token_json = excluded.token_json", (user_id, json.dumps(info)))


def drop_instagram_token(user_id):
    with connect() as con:
        con.execute("DELETE FROM instagram_tokens WHERE user_id = ?", (user_id,))
