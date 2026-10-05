"""
Pit Crew: run `python app.py`, then open http://localhost:8000

This file only starts the server. The features live in their own files:
  pipeline/   making Shorts (transcribe, moments, editing, captions, thumbnails...), no web code
  youtube/    everything that talks to YouTube and Google sign-in
  accounts/   the accounts database
  web/        the web routes, one file per feature (each adds its routes to web/server.py's app)
  static/     the page: index.html + sections/, css/ and js/ (one file per screen or feature)
See CLAUDE.md for where each feature lives.
"""
import sys
import threading
import webbrowser

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")  # before anything reads its settings (even settings.py)
sys.stdout.reconfigure(line_buffering=True)  # log lines appear at once, also when written to a file

from settings import JOBS_DIR  # noqa: E402

JOBS_DIR.mkdir(parents=True, exist_ok=True)

from web.server import app  # noqa: E402,F401
# Importing a web/ file adds its routes to the app. A new feature file must be added here.
from web import (  # noqa: E402,F401
    accounts,
    add_short,
    analytics,
    hooks,
    instagram_connect,
    instagram_posting,
    job_status,
    make_shorts,
    on_youtube,
    pages,
    password_reset,
    posting,
    preview,
    thumbnail_look,
    try_again,
    vlogs,
    vlog_info,
    youtube_connect,
)

if __name__ == "__main__":
    url = "http://localhost:8000"
    print(f"\n  Pit Crew is running at {url}\n  Keep this window open while you use it.\n")
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=8000, debug=False, threaded=True)
