"""
How far a Short's remake has got, for the editor's progress ring (js/editor.js): GET /api/remake/<job>/<idx> ->
{"pct": 0-100 | null}. null = saved, not rendering yet (waiting for the Short before it, or finding the frames): the ring
just spins. Kept in memory only: it's only true while the render runs in this process, and writing it into job.json
several times a second would also count as an edit (web/retention.py).
"""
from flask import jsonify

from pipeline.ffmpeg import watching
from web.server import app

PCT = {}  # (job id, Short's idx) -> percent done


def tracking(job_id, idx, total):
    """The FFmpeg runs in this block report to PCT; `total` is the Short's length in seconds."""
    def on_time(seconds):
        PCT[(job_id, idx)] = min(99, round(seconds / max(total, 0.1) * 100))
    return watching(on_time=on_time)


def done(job_id, idx):
    PCT.pop((job_id, idx), None)


@app.get("/api/remake/<job_id>/<int:idx>")
def remake_progress(job_id, idx):
    return jsonify(pct=PCT.get((job_id, idx)))
