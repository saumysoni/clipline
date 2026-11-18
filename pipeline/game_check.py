"""
Game Mode, step 3 (the only paid step): the AI looks at a few pictures of the best candidates and confirms, ranks and
names them (gaming.md). Never the whole stream: CHECK_FRAMES pictures per candidate, the middle third of the picture
(where a 9:16 Short looks), 480 high, plus what the streamer says in it.

Goes through ai_json() (gotcha 11: AI_PROVIDER, retries, fallbacks). Hooks keep HOOK_RULE and hook_fields() (gotcha 13).
check() never fails a run: no AI, a refusal or nonsense = the candidates as the signals ranked them, with plain labels.
Returns the candidates it kept, best first, each with "label", "title", hooks, "thumb_line1/2", "hashtags", "ai".
"""
import subprocess
from pathlib import Path

from pipeline.ai import ai_json, image_part
from pipeline.ffmpeg import ffmpeg_exe
from pipeline.game_moments import NAMES, label as plain_label
from pipeline.hooks import HOOK_RULE, hook_fields
from pipeline.pieces import said
from pipeline.text import fmt_mmss

CHECK_FRAMES = 3
TIMEOUT = 90  # seconds for the AI's answer (it reads ~45 small pictures)

PROMPT = """You check gameplay highlights from a {game} stream for vertical Shorts / Reels. Below are {n} candidate
moments a detector found from sound, motion and the game's screen (police chase, wanted level, WASTED, MISSION PASSED),
each with {k} pictures (the middle of the screen) and what the streamer says in it.

For each moment decide whether it's really a highlight a viewer would enjoy (action, a chase, a crash, a death, a
funny or big reaction), and rank the kept ones (1 = best). {hook_rule}

Return ONLY a JSON object: {{"items": [one object per moment:
  {{"id": the moment's number, "keep": true or false, "rank": 1..n for kept ones,
   "label": what happens, max 8 words, from the pictures (e.g. "police chase ends in a crash"),
   "title": a Short title, max 70 characters, no hashtags,
   "hooks": {{"curiosity": ..., "bold": ..., "story": ...}} on-screen hook ideas, each max 6 words,
   "hook_pick": "curiosity" | "bold" | "story",
   "thumb_line1": 1-3 words or "", "thumb_line2": 1-3 words,
   "hashtags": 3-5 words without #}}]}}

The moments:
{moments}"""


def frames(video_path, m, k=CHECK_FRAMES):
    """JPEG bytes of k pictures spread over the moment's pieces, the middle third of the picture, 480 high."""
    pieces = m.get("pieces") or [[m["start"], m["end"]]]
    total = sum(b - a for a, b in pieces)
    out = []
    for j in range(k):
        t = total * (j + 0.5) / k
        for a, b in pieces:  # the moment on its own clock -> stream seconds
            if t <= b - a:
                at = a + t
                break
            t -= b - a
        else:
            at = pieces[-1][1] - 0.5
        p = subprocess.run([ffmpeg_exe(), "-nostdin", "-hide_banner", "-loglevel", "error", "-ss", f"{at:.2f}",
                            "-i", str(Path(video_path).resolve()), "-frames:v", "1",
                            "-vf", "scale=-2:480,crop=iw/3:ih", "-q:v", "5", "-f", "image2pipe", "-c:v", "mjpeg", "-"],
                           stdin=subprocess.DEVNULL, capture_output=True, timeout=60)
        if p.returncode == 0 and p.stdout:
            out.append(p.stdout)
    return out


def _describe(k, m, transcript):
    kind = f"a montage of {len(m['pieces'])} parts" if m.get("montage") else "one clip"
    why = ", ".join(NAMES.get(w, w) for w in m.get("why") or []) or "general action"
    words = said(transcript, m)[:400] if transcript else ""
    return (f"Moment {k}: {kind}, {fmt_mmss(m['start'])}-{fmt_mmss(m['end'])}, detector saw: {why}. "
            f"Streamer says: \"{words or '(nothing)'}\"")


def plain(m, transcript=None):
    """A candidate ready without the AI: a label and title from its signals, no hooks."""
    text = plain_label(m)
    return {**m, "label": text, "title": text[:70], "hooks": {}, "hook_style": "custom", "hook": "", "hook_mode": "none",
            "thumb_line1": "", "thumb_line2": text.split(":")[-1].split("·")[0].strip()[:30].upper(),
            "hashtags": ["gaming", "gta5", "gta", "shorts"], "ai": False}


def check(video_path, cands, transcript, game_name, progress=lambda pct, msg: None, usage=None):
    """The candidates the AI kept, best first (see the top of this file). usage: a dict filled with what the check
    cost (pictures sent, provider, model, tokens; gaming.md "Track token cost per job")."""
    usage = {} if usage is None else usage
    if not cands:
        return []
    parts, numbered = [], []
    for k, m in enumerate(cands, 1):
        progress(k / len(cands) * 60, f"Looking at moment {k} of {len(cands)}")
        try:
            pics = frames(video_path, m)
        except (OSError, subprocess.SubprocessError) as e:
            print(f"Game Mode: couldn't grab pictures of moment {k}: {e}")
            pics = []
        numbered.append(_describe(k, m, transcript))
        for j, pic in enumerate(pics):
            parts += [f"Moment {k}, picture {j + 1}:", image_part(pic)]
    text = PROMPT.format(game=game_name, n=len(cands), k=CHECK_FRAMES, hook_rule=HOOK_RULE, moments="\n".join(numbered))
    progress(70, "Asking the AI which moments are best")
    usage.update(moments=len(cands), pictures=len(parts) // 2)
    try:
        raw = ai_json([text, *parts], temperature=0.4, timeout=TIMEOUT, busy_waits=[5], usage=usage)
    except Exception as e:  # noqa: BLE001  (never fail the run over the check: the signals' order stands)
        usage["failed"] = True
        print(f"Game Mode: the AI check didn't work ({e}); using the detector's order.")
        return [plain(m, transcript) for m in cands]
    items = raw.get("items") if isinstance(raw, dict) else raw
    items = items if isinstance(items, list) else []
    by_id = {}
    for it in items:
        try:
            by_id[int(it.get("id"))] = it
        except (TypeError, ValueError, AttributeError):
            continue
    if not by_id:
        print("Game Mode: the AI's answer had no usable moments; using the detector's order.")
        return [plain(m, transcript) for m in cands]
    kept = []
    for k, m in enumerate(cands, 1):
        it = by_id.get(k)
        if it is None or not it.get("keep", True):
            continue
        base = plain(m, transcript)
        hooks = hook_fields(it, said(transcript, m) if transcript else "")
        try:
            rank = int(it.get("rank") or 999)
        except (TypeError, ValueError):
            rank = 999
        kept.append((rank, -m["score"], {
            **base, **hooks,
            "label": " ".join(str(it.get("label") or base["label"]).split())[:80],
            "title": " ".join(str(it.get("title") or base["title"]).split())[:90],
            "thumb_line1": str(it.get("thumb_line1") or "")[:30],
            "thumb_line2": str(it.get("thumb_line2") or base["thumb_line2"])[:30],
            "hashtags": [h for h in ("".join(c for c in str(h) if c.isalnum() or c == "_")
                                     for h in (it.get("hashtags") or [])[:5]) if h] or base["hashtags"],
            "ai": True}))
    if not kept:  # the AI turned everything down: still give the creator the detector's best
        print("Game Mode: the AI kept no moment; using the detector's order.")
        return [plain(m, transcript) for m in cands]
    kept.sort(key=lambda x: (x[0], x[1]))
    return [m for _, _, m in kept]
