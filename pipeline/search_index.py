"""
Search by meaning (Ask your vlog): each vlog's passages (what was said, in ~15-second stretches, and each scene note
of what's seen) as embedding vectors, saved in search_index.npz (a few hundred KB, kept like the transcript).
Rebuilt by itself when the passages or the embedding model change (e.g. scene notes arrive later).
"""
import hashlib
import json
from pathlib import Path

import numpy as np

from pipeline.ai import ai_embed, embed_model

WINDOW = 15.0  # seconds of talk per passage: enough context for meaning, short enough to point at a moment


def passages(job_dir):
    """[{"t", "end", "text", "kind": "said" | "seen"}] of a vlog."""
    job_dir = Path(job_dir)
    out = []
    try:
        segs = [s for s in json.loads((job_dir / "transcript.json").read_text(encoding="utf-8")).get("segments", [])
                if s.get("text", "").strip()]
    except (OSError, ValueError):
        segs = []
    cur = []
    for s in segs:
        if cur and s["e"] - cur[0]["s"] > WINDOW:
            out.append({"t": cur[0]["s"], "end": cur[-1]["e"], "text": " ".join(x["text"].strip() for x in cur), "kind": "said"})
            cur = []
        cur.append(s)
    if cur:
        out.append({"t": cur[0]["s"], "end": cur[-1]["e"], "text": " ".join(x["text"].strip() for x in cur), "kind": "said"})
    try:
        for n in json.loads((job_dir / "scenes.json").read_text(encoding="utf-8")):
            out.append({"t": n["t"], "end": n["t"] + 10, "text": n["text"], "kind": "seen"})
    except (OSError, ValueError, KeyError):
        pass
    return out


def _sig(items, model):
    return hashlib.sha1((model + "\n" + "\n".join(f"{p['kind']}|{p['t']}|{p['text']}" for p in items)).encode()).hexdigest()


def load_index(job_dir, build=True):
    """(passages, unit vectors as an array) for a vlog, building or rebuilding the index when needed (one AI request).
    (None, None) if there's nothing to search, or build=False and it isn't ready."""
    job_dir = Path(job_dir)
    items = passages(job_dir)
    if not items:
        return None, None
    model = embed_model()
    sig, path = _sig(items, model), job_dir / "search_index.npz"
    if path.exists():
        try:
            z = np.load(path, allow_pickle=False)
            if str(z["sig"]) == sig:
                return items, z["vecs"].astype(np.float32)
        except (OSError, ValueError, KeyError):
            pass
    if not build:
        return None, None
    vecs = np.array(ai_embed([p["text"] for p in items]), dtype=np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9
    tmp = path.with_suffix(".part.npz")
    np.savez_compressed(tmp, vecs=vecs.astype(np.float16), sig=np.array(sig))
    tmp.replace(path)
    return items, vecs
