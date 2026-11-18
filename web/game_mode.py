"""
Game Mode v1 (gaming.md): a recorded gameplay stream (GTA V for now) becomes Shorts / Reels from what happens on screen
and in the sound, not only from what's said. It's an ordinary Shorts run (web/make_shorts.py) with job["game"] set
(the setup form's "Gaming stream" choice): only the step that picks the moments differs, game_moments() below.

  1. signals for every second (pipeline/game_signals.py): the stream read in CHUNK-second pieces, each through
     run.doing() so Pause / Stop leave at once (gotcha 36); saved in game_signals.json so Resume doesn't read it again
  2. score, candidates, montages (pipeline/game_moments.py)
  3. the facecam, if any (pipeline/game_frame.py)
  4. the AI check of the best ~15 (pipeline/game_check.py: a few middle-third pictures each, never the whole stream);
     no AI = the detector's order
  5. the Shorts: titles, hooks, hashtags from the check, Reframe settings (Split with a facecam, else a frame that
     follows the action), and `cx` so the vlog face finder never locks on the facecam

Montages are ordinary Shorts with several pieces (gotcha 30); the detector's details stay on the Short as s["game"].
"""
import json

import pipeline
from settings import JOBS_DIR

from pipeline.text import fmt_mmss

SIGNALS_FILE = "game_signals.json"
MAX_MONTAGES = 1  # per vlog, and only when 3 or more Shorts are asked for; it never repeats another Short's moment


def _parts(m):
    return m.get("pieces") or [[m["start"], m["end"]]]


def _overlaps(m, taken):
    """Does any part of m show what a taken moment shows? (A montage's gaps between its parts don't count.)"""
    return any(a < d and c < b for a, b in _parts(m) for t in taken for c, d in _parts(t))


MAP_MIN = 2.0  # seconds: the minimap is shown in stretches at least this long (no flicker on a quick cut)


def minimap_on(ps, m):
    """The vlog-second stretches of moment m when the minimap is really on screen (game_signals "map"; streams scanned
    before it existed: all of it). Also used for the corner graphics ({"map": their "seen"})."""
    seen = ps.get("map")
    if seen is None:
        return [[m["start"], m["end"]]]
    on = []
    for k in range(int(m["start"]), min(len(seen), int(m["end"]) + 1)):
        if seen[k] < 0.5:
            continue
        if on and k <= on[-1][1] + 1:  # (a one-second miss doesn't split a stretch)
            on[-1][1] = k + 1
        else:
            on.append([k, k + 1])
    return [[max(a, m["start"]), min(b, m["end"])] for a, b in on if b - a >= MAP_MIN]


def signals(job_id, src, meta, tr, game, run, step):
    """Every second's signals: read from the stream (or from game_signals.json, saved by an earlier, paused run)."""
    path = JOBS_DIR / job_id / SIGNALS_FILE
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        if abs(saved["duration"] - meta["duration"]) < 1:
            return saved
    except (OSError, ValueError, KeyError, TypeError):
        pass
    dur = meta["duration"]
    pictures, loud, prev, a = [], {}, None, 0.0
    while a < dur:
        b = min(dur, a + pipeline.GAME_CHUNK)
        step(pct=round(a / dur * 60), msg=f"Watching the gameplay: {fmt_mmss(a)} of {fmt_mmss(dur)}")
        got, prev = run.doing(pipeline.game_scan, src, a, b, game, prev)
        pictures += got
        loud.update(run.doing(pipeline.game_loudness, src, a, b))
        a = b
    ps = pipeline.game_per_second(pictures, loud, pipeline.keyword_hits(tr["words"], game["keywords"]), dur, game)
    step(pct=62, msg="Looking for the streamer's camera")
    ps["facecam"] = run.doing(pipeline.find_facecam, src, dur)
    tmp = path.with_name(SIGNALS_FILE + ".tmp")
    tmp.write_text(json.dumps(ps), encoding="utf-8")
    tmp.replace(path)
    return ps


def game_moments(job_id, src, meta, tr, count, game_name, run, step, taken=()):
    """The moments for `count` Shorts of a gameplay stream (best first), ready for render_short."""
    game = pipeline.load_game(game_name)
    ps = signals(job_id, src, meta, tr, game, run, step)
    step(pct=65, msg="Scoring the moments")
    found, monts, _ = pipeline.game_plan(ps, game, count)
    found = [m for m in found if not _overlaps(m, taken)]
    if not found and not monts:
        raise RuntimeError("Pit Crew couldn't find highlights in this stream. Check it's a GTA V stream, or make "
                           "Shorts from it as a normal video.")
    segs = tr.get("segments") or []  # each moment from the start of what's being said (pipeline/game_moments.py)
    found = pipeline.game_with_context(found, segs, game, meta["duration"])
    cands = found[:max(count * 2, 6)] + (monts[:MAX_MONTAGES] if count >= 3 else [])
    usage = {}
    checked = run.doing(pipeline.check_game, src, cands, tr, game["name"],
                        lambda p, m: step(pct=65 + round(p * 0.3), msg=m), usage=usage)
    if usage:  # what the AI check cost, kept on the job (gaming.md: "Track token cost per job")
        step(game_ai=usage)
        print(f"Game Mode AI check: {usage.get('pictures', 0)} picture(s), {usage.get('input_tokens', 0)} tokens in, "
              f"{usage.get('output_tokens', 0)} out ({usage.get('provider', '?')} {usage.get('model', '')}).")
    picked, montage = [], 0
    for m in checked:
        if len(picked) == count:
            break
        if _overlaps(m, picked) or (m.get("montage") and montage >= MAX_MONTAGES):
            continue  # (every Short shows something new: a real stream's action comes in bursts)
        montage += bool(m.get("montage"))
        picked.append(m)
    out = []
    for m in picked:
        cx, reframe = pipeline.game_framing(m, ps["x"], meta, ps.get("facecam"))
        if reframe and reframe["layout"] == "fill":  # a frame that changes through the Short (pipeline/game_frame.py)
            moving = run.doing(pipeline.game_auto_frame, src, meta, m, ps["x"])
            if moving and moving["moves"]:
                reframe, cx = moving, moving["moves"][0]["x"] * meta["width"]
        moment = {
            "start": m["start"], "end": m["end"],
            **({"pieces": m["pieces"]} if len(m["pieces"]) > 1 else {}),
            "title": m["title"], "why": m["label"],
            "hooks": m.get("hooks") or {}, "hook_style": m.get("hook_style", "custom"), "hook": m.get("hook", ""),
            "hook_mode": m.get("hook_mode", "none"),
            "thumb_line1": m.get("thumb_line1", ""), "thumb_line2": m.get("thumb_line2", ""),
            "hashtags": m.get("hashtags") or [],
            "cx": round(cx, 1),
            "hud": {"minimap": game["regions"]["minimap"],  # laid over the Short (pipeline/game_hud.py)
                    "spot": "high" if reframe and reframe.get("wide") else "low", "on": minimap_on(ps, m),
                    "extras": [{"box": o["box"], "on": minimap_on({"map": o["seen"]}, m)}
                               for o in ps.get("overlays") or []]},
            "game": {"game": game_name, "label": m["label"], "score": m["score"], "signals": m.get("why") or [],
                     "montage": bool(m.get("montage")), "segments": m.get("segments") or [], "ai": m.get("ai", False),
                     "facecam": ps.get("facecam")},
        }
        if reframe:
            moment["reframe"] = pipeline.clean_reframe(reframe, ps["duration"])
        out.append(moment)
    print(f"Game Mode: {len(out)} Short(s) from {len(found)} moment(s) and {len(monts)} montage(s); "
          f"facecam {'found' if ps.get('facecam') else 'none'}.")
    return out
