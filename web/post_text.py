"""
What's posted with a Short: its hashtags (shared by YouTube and Instagram) and its Instagram caption. The editor card
reads and saves them here as the creator types (js/post-text.js); the YouTube title has its own route
(web/clips.py clip_title).

"Generate ideas" under the title and the caption asks the AI for three options (pipeline/post_suggest.py); nothing is
saved until the creator picks one (which then saves like typing).

A Short's "ig_caption" is only stored once the creator writes their own: until then the caption is suggested
(instagram/publish.py suggested_caption: title, where the full video is), so it follows title edits.
Try again makes a new Short, so its caption and hashtags start fresh.
"""
import json
import re

from flask import jsonify, request

import instagram as ig
import pipeline
from settings import JOBS_DIR
from web.server import app
from web.store import LOCK, load_job, update_short

TAG_MAX = 50  # characters in one hashtag


def _short(job_id, idx):
    with LOCK:
        job = load_job(job_id)
        s = next((x for x in (job or {}).get("shorts", []) if x["idx"] == idx and not x.get("pending")), None)
        return (dict(job), dict(s)) if s else (None, None)


def _ig_state(job, idx):
    """Where the Short is on Instagram: "posted" (the caption can't change any more), "planned", or ""."""
    p = next((x for x in job.get("ig_posts") or [] if x["idx"] == idx), None)
    return "" if not p else "posted" if p["status"] in ("done", "posting", "check") else "planned" if p["status"] == "waiting" else ""


def clean_tags(raw):
    """Hashtags as typed (a list, or text like "#hiking snow, travel") -> words without "#", no repeats."""
    words = raw if isinstance(raw, list) else re.split(r"[\s,]+", str(raw or ""))
    out, seen = [], set()
    for w in words:
        t = re.sub(r"[^\w]", "", str(w).strip().lstrip("#"))[:TAG_MAX]
        if t and t.lower() not in seen:
            out.append(t); seen.add(t.lower())
    return out


@app.get("/api/clips/<job_id>/<int:idx>/post-text")
def post_text_get(job_id, idx):
    job, s = _short(job_id, idx)
    if not s:
        return jsonify(error="That Short isn't available any more."), 404
    return jsonify(caption=s.get("ig_caption") or "", suggested=ig.suggested_caption(s, job.get("vlog")),
                   hashtags=s.get("hashtags") or [], instagram=_ig_state(job, idx))


@app.post("/api/clips/<job_id>/<int:idx>/post-text")
def post_text_save(job_id, idx):
    """{"caption": text ("" = use the suggested one again), "hashtags": [...]}; either may be left out."""
    data = request.get_json(silent=True) or {}
    job, s = _short(job_id, idx)
    if not s:
        return jsonify(error="That Short isn't available any more."), 404
    change = {}
    if "caption" in data:
        text = str(data.get("caption") or "").strip()
        if len(text) > ig.MAX_CAPTION:
            return jsonify(error=f"Instagram captions can be up to {ig.MAX_CAPTION:,} characters. Shorten it a little."), 400
        suggested = ig.suggested_caption(s, job.get("vlog")).strip()
        change["ig_caption"] = None if not text or text == suggested else text
    if "hashtags" in data:
        tags = clean_tags(data.get("hashtags"))
        if len(tags) > ig.MAX_TAGS:
            return jsonify(error=f"Instagram allows {ig.MAX_TAGS} hashtags. Remove a few."), 400
        change["hashtags"] = tags
    if change:
        update_short(job_id, idx, **change)
    return post_text_get(job_id, idx)


@app.post("/api/clips/<job_id>/<int:idx>/suggest")
def post_text_suggest(job_id, idx):
    """{"kind": "title" | "caption"} -> {"items": [three ideas]}. Works without the vlog's video (only words)."""
    kind = str((request.get_json(silent=True) or {}).get("kind", ""))
    job, s = _short(job_id, idx)
    if not s:
        return jsonify(error="That Short isn't available any more."), 404
    try:
        tr = json.loads((JOBS_DIR / job_id / "transcript.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        tr = None  # the ideas then come from the title and hook
    try:
        items = pipeline.suggest_post_text(kind, s, tr, job.get("vlog"))
    except RuntimeError as e:
        return jsonify(error=str(e)), 400
    return jsonify(items=items)
