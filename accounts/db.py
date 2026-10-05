"""
Accounts database (SQLite): who can sign in, and each person's YouTube and Instagram connections.

SQLite from Python's standard library, in data/clipline.db (DATABASE_PATH). One row per user;
the YouTube token is stored per user so every creator posts to their own channel.
"""
import hashlib
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
CREATE TABLE IF NOT EXISTS connections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    account_id TEXT,
    token_json TEXT NOT NULL,
    profile_json TEXT,
    active INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    UNIQUE (user_id, platform, account_id)
);
CREATE TABLE IF NOT EXISTS password_resets (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at REAL NOT NULL
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
        if con.execute("PRAGMA user_version").fetchone()[0] < 1:
            _move_to_connections(con)
            con.execute("PRAGMA user_version = 1")


def _move_to_connections(con):
    """Once (PRAGMA user_version 0 -> 1): copy the old one-per-user youtube_tokens / instagram_tokens rows into
    connections. The old tables are left as they were (unused), so nothing is lost."""
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    if "youtube_tokens" in tables:
        for r in con.execute("SELECT user_id, token_json, channel_json FROM youtube_tokens").fetchall():
            channel = json.loads(r["channel_json"]) if r["channel_json"] else None
            con.execute("INSERT OR IGNORE INTO connections (user_id, platform, account_id, token_json, profile_json, "
                        "active, created_at) VALUES (?, 'youtube', ?, ?, ?, 1, ?)",
                        (r["user_id"], (channel or {}).get("id"), r["token_json"], r["channel_json"], time.time()))
    if "instagram_tokens" in tables:
        for r in con.execute("SELECT user_id, token_json FROM instagram_tokens").fetchall():
            ig_id = json.loads(r["token_json"]).get("ig_id")
            con.execute("INSERT OR IGNORE INTO connections (user_id, platform, account_id, token_json, active, "
                        "created_at) VALUES (?, 'instagram', ?, ?, 1, ?)",
                        (r["user_id"], ig_id, r["token_json"], time.time()))


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


RESET_HOURS = 1


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def new_password_reset(user_id):
    """A one-time reset token for this user (only its hash is stored), valid for RESET_HOURS."""
    token = secrets.token_urlsafe(32)
    with connect() as con:
        con.execute("DELETE FROM password_resets WHERE expires_at < ?", (time.time(),))
        con.execute("INSERT INTO password_resets (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                    (_hash(token), user_id, time.time() + RESET_HOURS * 3600))
    return token


def reset_password(token, password_hash):
    """Use a reset token: set the new password and return the user, or None if the token is unknown or expired.
    Opening the link proves the email is theirs, so it counts as verified, every reset link of theirs stops
    working and every old session ends (someone who signed up with this email first is locked out)."""
    with connect() as con:
        row = con.execute("SELECT user_id FROM password_resets WHERE token_hash = ? AND expires_at >= ?",
                          (_hash(token), time.time())).fetchone()
        if not row:
            return None
        con.execute("DELETE FROM password_resets WHERE user_id = ?", (row["user_id"],))
        con.execute("UPDATE users SET password_hash = ?, email_verified = 1, session_version = session_version + 1 "
                    "WHERE id = ?", (password_hash, row["user_id"]))
    return user_by_id(row["user_id"])


# Connected YouTube channels and Instagram accounts ("platform" youtube / instagram). A user can connect several
# of each; one per platform is "active" (where new posts go). account_id is the YouTube channel id or Instagram
# user id. Rows moved from the old tables may have no YouTube channel id yet (youtube/connection.py fills it in).

def _conn(row):
    if not row:
        return None
    d = dict(row)
    d["token"] = json.loads(d.pop("token_json"))
    d["profile"] = json.loads(d.pop("profile_json") or "null")
    d["active"] = bool(d["active"])
    return d


def connections(user_id, platform):
    """This user's connections on a platform, oldest first."""
    with connect() as con:
        return [_conn(r) for r in con.execute("SELECT * FROM connections WHERE user_id = ? AND platform = ? "
                                              "ORDER BY created_at, id", (user_id, platform))]


def connection(user_id, platform, account_id=None):
    """One connection: the one for account_id, or (account_id None) the active one. None if not connected."""
    with connect() as con:
        if account_id:
            row = con.execute("SELECT * FROM connections WHERE user_id = ? AND platform = ? AND account_id = ?",
                              (user_id, platform, account_id)).fetchone()
        else:
            row = con.execute("SELECT * FROM connections WHERE user_id = ? AND platform = ? "
                              "ORDER BY active DESC, created_at DESC, id DESC LIMIT 1", (user_id, platform)).fetchone()
    return _conn(row)


def save_connection(user_id, platform, account_id, token, profile=None):
    """Add (or update, if this account is already connected) a connection and make it the active one."""
    token_json = token if isinstance(token, str) else json.dumps(token)
    profile_json = None if profile is None else json.dumps(profile)
    with connect() as con:
        con.execute("UPDATE connections SET active = 0 WHERE user_id = ? AND platform = ?", (user_id, platform))
        con.execute("INSERT INTO connections (user_id, platform, account_id, token_json, profile_json, active, "
                    "created_at) VALUES (?, ?, ?, ?, ?, 1, ?) ON CONFLICT(user_id, platform, account_id) DO UPDATE SET "
                    "token_json = excluded.token_json, profile_json = COALESCE(excluded.profile_json, profile_json), "
                    "active = 1", (user_id, platform, account_id, token_json, profile_json, time.time()))


def update_connection(conn_id, token=None, profile=None):
    """Save a refreshed token and/or new profile for one connection."""
    with connect() as con:
        if token is not None:
            con.execute("UPDATE connections SET token_json = ? WHERE id = ?",
                        (token if isinstance(token, str) else json.dumps(token), conn_id))
        if profile is not None:
            con.execute("UPDATE connections SET profile_json = ? WHERE id = ?", (json.dumps(profile), conn_id))


def set_account_id(conn_id, account_id, profile):
    """Give a moved-over YouTube row its channel id. If that channel is connected twice, keep the newer row
    (its token is the fresher one) and drop this one. Returns the id of the row that's kept."""
    with connect() as con:
        me = con.execute("SELECT user_id, platform, active FROM connections WHERE id = ?", (conn_id,)).fetchone()
        if not me:
            return None
        twin = con.execute("SELECT id FROM connections WHERE user_id = ? AND platform = ? AND account_id = ?",
                           (me["user_id"], me["platform"], account_id)).fetchone()
        if twin:
            con.execute("DELETE FROM connections WHERE id = ?", (conn_id,))
            if me["active"]:
                con.execute("UPDATE connections SET active = 1 WHERE id = ?", (twin["id"],))
            return twin["id"]
        con.execute("UPDATE connections SET account_id = ?, profile_json = ? WHERE id = ?",
                    (account_id, json.dumps(profile), conn_id))
        return conn_id


def set_active(user_id, platform, account_id):
    """Make account_id the active connection. False if this user hasn't connected it."""
    with connect() as con:
        if not con.execute("SELECT 1 FROM connections WHERE user_id = ? AND platform = ? AND account_id = ?",
                           (user_id, platform, account_id)).fetchone():
            return False
        con.execute("UPDATE connections SET active = CASE WHEN account_id = ? THEN 1 ELSE 0 END "
                    "WHERE user_id = ? AND platform = ?",
                    (account_id, user_id, platform))
    return True


def drop_connection(conn_id):
    """Forget one connection. If it was the active one, the most recently added other one becomes active."""
    with connect() as con:
        me = con.execute("SELECT user_id, platform, active FROM connections WHERE id = ?", (conn_id,)).fetchone()
        if not me:
            return
        con.execute("DELETE FROM connections WHERE id = ?", (conn_id,))
        if me["active"]:
            con.execute("UPDATE connections SET active = 1 WHERE id = (SELECT id FROM connections WHERE user_id = ? "
                        "AND platform = ? ORDER BY created_at DESC, id DESC LIMIT 1)", (me["user_id"], me["platform"]))
