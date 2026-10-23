"""
GET /healthz: is Pit Crew up? For the uptime monitor and the update script (deploy/update.sh waits for it after a
restart and rolls back if it never answers). Public, and says nothing about anyone: only "ok" or what's wrong
(database unreadable, disk nearly full, the vlog queue not running).
"""
import shutil
import threading

from flask import jsonify

from accounts import db
from settings import JOBS_DIR

from web.server import app

LOW_DISK_GB = 5  # under this, new vlogs would start failing (a long vlog plus its Shorts can take a few GB)


@app.get("/healthz")
def healthz():
    problems = []
    try:
        db.ping()
    except Exception:  # noqa: BLE001
        problems.append("database")
    try:
        free = shutil.disk_usage(JOBS_DIR).free / 1e9
        if free < LOW_DISK_GB:
            problems.append(f"disk ({free:.1f} GB free)")
    except OSError:
        problems.append("jobs folder")
    if not any(t.name.startswith("job-queue") for t in threading.enumerate()):
        problems.append("vlog queue")
    return (jsonify(ok=False, problems=problems), 503) if problems else jsonify(ok=True)
