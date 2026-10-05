"""
Ask your vlog: "when was I climbing the mountain?" answered from what was said (the transcript) and what's seen
(scene notes, pipeline/scene_notes.py), with times to watch or turn into a Short. Plus search across every vlog
(plain word matching, no AI: instant and free).

job["scenes"]: None, "making" (with job["scenes_pct"]), "ready", or an error message. Scene notes are made in the
background after the Shorts are ready (they never slow the Shorts down), or on request for older vlogs.
"""
import json
import re
import threading
import traceback

import numpy as np
from flask import abort, g, jsonify, request

import pipeline
from pipeline.ai import ai_embed, ai_json
from pipeline.scene_notes import enabled as scenes_enabled, make_scene_notes
from pipeline.search_index import load_index
from pipeline.text import fmt_mmss
from settings import JOBS_DIR

from web.server import app
from web.store import LOCK, load_job, update
from web.vlogs import user_jobs

MAKING = set()  # vlogs whose scene notes are being made (in this process)


def start_scene_notes(job_id):
    """Make scenes.json in the background, unless it exists, is under way, the video is gone or it's turned off."""
    job_dir = JOBS_DIR / job_id
    src = next(job_dir.glob("source.*"), None)
    if not scenes_enabled() or not src or (job_dir / "scenes.json").exists():
        build_index_later(job_id)
        return False
    with LOCK:
        if job_id in MAKING:
            return True
        MAKING.add(job_id)
        job = load_job(job_id)
    duration = (job or {}).get("duration") or pipeline.probe(src)["duration"]

    def run():
        try:
            update(job_id, scenes="making", scenes_pct=0)
            make_scene_notes(src, duration, job_dir / "scenes.json",
                             lambda pct, msg: update(job_id, scenes_pct=round(pct)))
            update(job_id, scenes="ready")
        except Exception as e:  # noqa: BLE001  (scene notes are a bonus: never fail anything else)
            traceback.print_exc()
            update(job_id, scenes=str(e) if isinstance(e, RuntimeError) else "Couldn't read the video's scenes.")
        finally:
            with LOCK:
                MAKING.discard(job_id)
            build_index_later(job_id)  # search by meaning, now with what's seen too
    threading.Thread(target=run, daemon=True).start()
    return True


def _notes(job_id):
    """(transcript lines, scene notes) of a vlog: [(seconds, text)] each."""
    job_dir = JOBS_DIR / job_id
    said, seen = [], []
    try:
        tr = json.loads((job_dir / "transcript.json").read_text(encoding="utf-8"))
        said = [(s["s"], s["text"].strip()) for s in tr.get("segments", []) if s.get("text", "").strip()]
    except (OSError, ValueError, KeyError):
        pass
    try:
        seen = [(n["t"], n["text"]) for n in json.loads((job_dir / "scenes.json").read_text(encoding="utf-8"))]
    except (OSError, ValueError, KeyError):
        pass
    return said, seen


def _status(job):
    job_dir = JOBS_DIR / job["id"]
    src = next(job_dir.glob("source.*"), None)
    s = job.get("scenes")
    if (job_dir / "scenes.json").exists():
        s = "ready"
    return {"scenes": s, "scenes_pct": job.get("scenes_pct", 0), "can_make": scenes_enabled() and s not in ("ready", "making")
            and bool(next(job_dir.glob("source.*"), None)), "video": bool(next(job_dir.glob("source.*"), None)),
            "preview": (job_dir / "preview.mp4").exists(), "youtube_url": (job.get("vlog") or {}).get("youtube_url", ""),
            "duration": job.get("duration"),
            # what Watch plays: the small copy when there is one (quick to seek), else the original, else nothing
            "play_url": f"/media/{job['id']}/preview.mp4" if (job_dir / "preview.mp4").exists()
            else f"/media/{job['id']}/{src.name}" if src else ""}


@app.get("/api/vlogs/<job_id>/ask")
def ask_status(job_id):
    with LOCK:
        job = load_job(job_id)
    if not job:
        abort(404)
    return jsonify(_status(job))


@app.post("/api/vlogs/<job_id>/scenes")
def scenes_start(job_id):
    with LOCK:
        job = load_job(job_id)
    if not job or job.get("status") != "ready":
        abort(400)
    if not next((JOBS_DIR / job_id).glob("source.*"), None):
        return jsonify(error="This vlog's video was deleted, so Pit Crew can't look at it. Upload it again first."), 400
    start_scene_notes(job_id)
    with LOCK:
        return jsonify(_status(load_job(job_id)))


ASK = ("You answer a creator's question about their own vlog, using only the notes below: what was said (from the "
       "transcript) and what is seen (notes made from frames every few seconds). Give the times where it happens. "
       "Never invent anything: if the notes don't show it, say you couldn't find it, and suggest what they could search "
       "for instead.\n\nReturn JSON: {{\"found\": true/false, \"answer\": \"one or two plain sentences, with times as "
       "m:ss\", \"moments\": [{{\"start\": seconds, \"end\": seconds, \"what\": \"a few words\"}}]}} (up to 5 moments, "
       "in the order they happen, each 5 to 90 seconds long).\n\nQuestion: {q}\n\nThe vlog is {dur} long.\n\n"
       "What was said:\n{said}\n\nWhat is seen:\n{seen}")


@app.post("/api/vlogs/<job_id>/ask")
def ask(job_id):
    q = str((request.get_json(silent=True) or {}).get("question", "")).strip()[:300]
    if len(q) < 3:
        return jsonify(error="Type a question, like: when was I climbing the mountain?"), 400
    with LOCK:
        job = load_job(job_id)
    if not job or job.get("status") != "ready":
        abort(400)
    said, seen = _notes(job_id)
    if not said and not seen:
        return jsonify(error="Pit Crew has nothing to search in this vlog yet."), 400
    dur = job.get("duration") or max([t for t, _ in said + seen] + [0])
    prompt = ASK.format(q=q, dur=fmt_mmss(dur),
                        said="\n".join(f"[{fmt_mmss(t)}] {x}" for t, x in said) or "(nothing was said)",
                        seen="\n".join(f"[{fmt_mmss(t)}] {x}" for t, x in seen) or "(no scene notes for this vlog)")
    try:
        raw = ai_json(prompt, temperature=0.2)
    except RuntimeError as e:
        return jsonify(error=str(e)), 502
    raw = raw if isinstance(raw, dict) else {}
    moments = []
    for m in raw.get("moments") or []:
        try:
            s, e = max(0.0, float(m["start"])), min(float(dur), float(m["end"]))
        except (KeyError, TypeError, ValueError):
            continue
        if e - s < 3:
            e = min(float(dur), s + 15)
        e = min(e, s + 90)  # a moment, not a whole section (and a sensible length for a Short)
        if e > s:
            moments.append({"start": round(s, 1), "end": round(e, 1), "what": str(m.get("what", ""))[:80]})
    moments.sort(key=lambda m: m["start"])
    return jsonify(answer=str(raw.get("answer") or "")[:600], found=bool(raw.get("found")) and bool(moments),
                   moments=moments[:5], used_scenes=bool(seen), **_status(job))


STOP = set("a an and are at be but by did do for from had has have i if in is it its me my of on or our so that the "
           "then there this to up was we were what when where which who will with you your about how".split())


def keyword_search(user_id, q):
    """Plain word matching: the fallback when the AI can't be reached."""
    q = q.strip().lower()[:200]
    words = [w for w in re.findall(r"[\w']+", q) if len(w) > 1 and w not in STOP]
    if not words:
        return [], []
    out = []
    for job in user_jobs(user_id):
        if job.get("status") != "ready":
            continue
        name = (job.get("vlog") or {}).get("title") or job.get("name") or "Your vlog"
        said, seen = _notes(job["id"])
        st = None
        for kind, rows in (("said", said), ("seen", seen)):
            for t, text in rows:
                low = text.lower()
                hits = sum(1 for w in words if re.search(r"\b" + re.escape(w), low))
                if hits:
                    st = st or _status(job)  # can its video still be played here, or on YouTube?
                    out.append({"job": job["id"], "vlog": name, "t": t, "text": text, "kind": kind,
                                "score": hits / len(words) + (0.1 if q in low else 0),
                                "video": st["video"], "play_url": st["play_url"], "youtube_url": st["youtube_url"]})
    out.sort(key=lambda r: (-r["score"], r["vlog"], r["t"]))
    return out[:40], words


EXPAND = ("A creator is searching their own travel/lifestyle vlogs for: \"{q}\"\n\nThe vlogs can only be searched through what "
          "was said (transcript) and short notes of what's seen in the video. Write up to 8 short phrases that would "
          "appear there if a moment matches the MEANING of the search (not its exact words): what someone might say, and "
          "what might be seen. Example: for \"where I found something ancient\" -> \"this temple is 700 years old\", "
          "\"centuries-old ruins\", \"old stone carvings\", \"history of this place\", \"ancient fort\".\n\n"
          "Return JSON: {{\"phrases\": [\"...\"]}}")
PICK = ("A creator searched their vlogs for: \"{q}\"\n\nBelow are candidate moments (what was said, or what's seen). "
        "Keep only the ones that truly match what the search MEANS, best first (at most 12). Sharing a word isn't "
        "enough: \"I found something weird\" doesn't match \"where I found something ancient\"; \"this temple is 700 years "
        "old\" does. For each, give a few words saying why it matches.\n\nReturn JSON: {{\"matches\": [{{\"id\": <number>, "
        "\"why\": \"...\"}}]}} (an empty list if none match).\n\n{cands}")
CANDIDATES = 50


def _vlog_indexes(jobs):
    """Each vlog's (passages, vectors), building missing ones a few at a time."""
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(4) as pool:
        return list(zip(jobs, pool.map(lambda j: load_index(JOBS_DIR / j["id"]), jobs)))


@app.get("/api/search")
def search():
    """Moments in any vlog that match what the search means: the AI widens the search into phrases, the closest
    passages by meaning are found, and the AI keeps the real matches. Falls back to word matching."""
    q = str(request.args.get("q", "")).strip()[:200]
    if len(q) < 2:
        return jsonify(items=[], words=[], mode="meaning")
    jobs = [j for j in user_jobs(g.user["id"]) if j.get("status") == "ready"]
    try:
        raw = ai_json(EXPAND.format(q=q.replace('"', "'")), temperature=0.3, busy_waits=[])
        phrases = [str(p)[:120] for p in (raw.get("phrases") if isinstance(raw, dict) else raw) or [] if str(p).strip()][:8]
        qv = np.array(ai_embed([q] + phrases, query=True), dtype=np.float32)
        qv /= np.linalg.norm(qv, axis=1, keepdims=True) + 1e-9
        cands = []
        for job, (items, vecs) in _vlog_indexes(jobs):
            if items is None:
                continue
            best = (vecs @ qv.T).max(axis=1)  # closest to the search or any of its phrases
            name = (job.get("vlog") or {}).get("title") or job.get("name") or "Your vlog"
            cands += [(float(best[k]), job, name, items[k]) for k in range(len(items))]
    except RuntimeError as e:
        print("Search by meaning unavailable, using word matching:", e)
        items, words = keyword_search(g.user["id"], q)
        return jsonify(items=items, words=words, mode="words")
    cands.sort(key=lambda c: -c[0])
    cands = cands[:CANDIDATES]
    if not cands:
        return jsonify(items=[], words=[], mode="meaning")
    listing = "\n".join(f"{n}. [{c[2]} at {fmt_mmss(c[3]['t'])}, {c[3]['kind']}] {c[3]['text'][:300]}" for n, c in enumerate(cands))
    try:
        raw = ai_json(PICK.format(q=q.replace('"', "'"), cands=listing), temperature=0.1, busy_waits=[])
        picks = [(int(m["id"]), str(m.get("why", ""))[:100]) for m in (raw.get("matches") if isinstance(raw, dict) else raw) or []
                 if str(m.get("id", "")).isdigit() and int(m["id"]) < len(cands)]
    except (RuntimeError, TypeError, ValueError, KeyError):
        picks = [(n, "") for n in range(min(12, len(cands)))]  # the AI didn't answer: closest by meaning
    out, seen_ids, st = [], set(), {}
    for n, why in picks:
        if n in seen_ids:
            continue
        seen_ids.add(n)
        _, job, name, p = cands[n]
        st[job["id"]] = st.get(job["id"]) or _status(job)
        out.append({"job": job["id"], "vlog": name, "t": p["t"], "text": p["text"], "kind": p["kind"], "why": why,
                    "video": st[job["id"]]["video"], "play_url": st[job["id"]]["play_url"],
                    "youtube_url": st[job["id"]]["youtube_url"]})
    return jsonify(items=out[:12], words=[], mode="meaning")


def build_index_later(job_id):
    """Index a vlog for search by meaning in the background (after its Shorts or scene notes are ready)."""
    def run():
        try:
            load_index(JOBS_DIR / job_id)
        except Exception as e:  # noqa: BLE001  (search builds it on first use instead)
            print("Couldn't index the vlog for search yet:", e)
    threading.Thread(target=run, daemon=True).start()
