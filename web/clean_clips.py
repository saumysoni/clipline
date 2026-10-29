"""
Clean clips (pipeline/clean_clip.py, gotcha 35): just before a vlog's video is deleted (web/vlogs.py remove_video(), by
the creator or by web/retention.py), every draft Short gets its moment and 30 s either side as a clip, s["clip"] =
{"file", "from", "to", "scale"}. After that the editor keeps working on it: source() is the one answer to "what video do
I remake this Short from" (the vlog while it's kept, else the Short's clip, else nothing).

Posted and planned Shorts don't get one (they can't be edited). The clip goes with its Short (web/retention.py
_short_files) and when the Short is deleted. Try again, Add a Short and reaching further than the clip still need the
vlog (they need other moments).
"""
import json
import traceback

import pipeline
from settings import JOBS_DIR

from web.store import JOBS, LOCK, load_job


def _vlog(job_id, job):
    if job.get("video_deleted_at"):
        return None
    return next((JOBS_DIR / job_id).glob("source.*"), None)


def source(job_id, job, me):
    """Where to remake this Short from: {"path", "offset" (the vlog second it starts at), "scale" (its picture width /
    the vlog's), "reach" (from, to) in vlog seconds, "clip" (True for a clip)}, or None (nothing left to remake from)."""
    src = _vlog(job_id, job)
    if src:
        return {"path": src, "offset": 0.0, "scale": 1.0, "reach": (0.0, float(job.get("duration") or 1e9)), "clip": False}
    c = me.get("clip") or {}
    f = JOBS_DIR / job_id / c.get("file", "") if c.get("file") else None
    if f and f.is_file():
        return {"path": f, "offset": float(c["from"]), "scale": float(c.get("scale") or 1), "reach": (float(c["from"]), float(c["to"])),
                "clip": True}
    return None


def scaled_cx(me, src):
    """The Short's face position (vlog pixels) in the source's pixels; "find" when there's none."""
    cx = me.get("cx")
    return cx * src["scale"] if isinstance(cx, (int, float)) else ("find" if cx is None else cx)


def make_clips(job_id):
    """Before the vlog's video goes: a clip for every draft Short that hasn't one. Never stops the deletion (a Short
    whose clip fails just can't be remade later, as before)."""
    with LOCK:
        job = load_job(job_id)
        if not job:
            return 0
        job = json.loads(json.dumps(job, default=str))
    src = next((JOBS_DIR / job_id).glob("source.*"), None)
    if not src or job.get("video_deleted_at"):
        return 0
    made = 0
    try:
        meta = pipeline.probe(src)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return 0
    duration = float(job.get("duration") or meta.get("duration") or 0)
    for s in job.get("shorts") or []:
        if s.get("pending") or s.get("clip") or not _is_draft(job, s):
            continue
        try:
            a, b = pipeline.clip_reach(pipeline.kept_pieces(s), duration)
            name = f"clip_{s['idx']}.mp4"  # one a Short (made once: the vlog goes right after)
            info = pipeline.make_clean_clip(src, meta, a, b, JOBS_DIR / job_id / name)
            with LOCK:
                live = JOBS.get(job_id) or load_job(job_id)
                for x in live["shorts"]:
                    if x["idx"] == s["idx"]:
                        x["clip"] = {"file": name, **info}
                (JOBS_DIR / job_id / "job.json").write_text(json.dumps(live, default=str), encoding="utf-8")
                job = json.loads(json.dumps(live, default=str))
            made += 1
        except Exception:  # noqa: BLE001
            print(f"Couldn't keep a clean clip of Short {s.get('idx')} of {job_id}:")
            traceback.print_exc()
    return made


def _is_draft(job, s):
    return not any(u["idx"] == s["idx"] for u in job.get("uploads") or []) and \
        not any(p["idx"] == s["idx"] for p in job.get("ig_posts") or [])


def render(src, moment, words, num, style, job_dir, me):
    """render_short from this source (source() above): the face position scaled into its pixels and back, so the Short
    keeps it in the vlog's. Returns (video file name, cx in the vlog's pixels)."""
    meta = pipeline.probe(src["path"])
    video, cx = pipeline.render_short(src["path"], meta, moment, words, num, style, job_dir, cx=scaled_cx(me, src),
                                      offset=src["offset"])
    if isinstance(cx, (int, float)) and src["scale"]:
        cx = cx / src["scale"]
    return video, cx


def in_reach(pieces, src):
    """These pieces (vlog seconds) inside what the source has; [] if none of them is."""
    a, b = src["reach"]
    return pipeline.normalize_pieces(pieces, a, b)
