"""
Game Mode's accept / reject log (gaming.md step 9: "Log accept/reject in job.json to tune weights later").

A game Short carries what the detector saw (s["game"]: label, score, signals, montage). A Short the creator keeps
stays in job["shorts"], so only the rejected ones need writing down before they're gone: a deleted draft
(web/clips.py) or one replaced by Try again (web/try_again.py) goes into job["game_log"]. game_verdicts() then gives
every game Short of a vlog with its verdict: "posted", "draft" (kept, not out yet), "deleted" or "tried_again".
Nothing here is shown to the creator; it's for tuning pipeline/games/<game>.json.
"""
import time

from web.retention import is_draft

LOG = "game_log"
MAX_LOG = 100  # per vlog (10 Shorts with every Try again is far fewer)


def _entry(s):
    gm = s.get("game") or {}
    return {"start": s.get("start"), "end": s.get("end"), "pieces": s.get("pieces"),
            "label": gm.get("label"), "score": gm.get("score"), "signals": gm.get("signals") or [],
            "montage": bool(gm.get("montage")), "ai": bool(gm.get("ai"))}


def note_rejected(job, s, how):
    """Write down a game Short the creator turned down (`how`: "deleted" or "tried_again"). Call with LOCK held, on
    the job that's about to be saved. Shorts that didn't come from Game Mode are left out."""
    if not s or not s.get("game") or s.get("pending"):
        return
    log = job.setdefault(LOG, [])
    log.append({**_entry(s), "verdict": how, "at": time.time()})
    del log[:-MAX_LOG]


def game_verdicts(job):
    """Every game Short of this vlog, kept or turned down, with its verdict."""
    out = [dict(e) for e in job.get(LOG) or []]
    for s in job.get("shorts") or []:
        if s.get("game") and not s.get("pending"):
            out.append({**_entry(s), "idx": s["idx"], "verdict": "draft" if is_draft(job, s) else "posted"})
    return out
