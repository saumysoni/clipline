"""
Game Mode, step 1: cheap signals for every second of a gameplay stream, on the processor only (gaming.md).

Pictures: the stream is read in chunks (CHUNK seconds; the caller checks Pause / Stop between them, gotcha 36) at 320x180,
from its keyframes when they come every <= KEY_GAP s (recorded streams usually have one every 2 s: nothing else is
decoded, gotcha 37), else one picture a second. Each picture gives, from the game's config (pipeline/games/<game>.json):
  motion   how much the picture changed since the last one; cut = a big change (a new scene)
  police   red and blue in the minimap (it flashes while the police chase)
  stars    white in the wanted-stars corner (more stars = more of it)
  grey     a grey picture: the WASTED / BUSTED screen, or the pause map (told apart by `edges`: the map is full of thin
           road lines) or a black loading screen (`bright`); gold = yellow-orange in the middle (fire, an explosion or
           MISSION PASSED's word: the colour alone can't tell them apart)
  x        where in the picture the motion is (0-1), for a crop that follows the action
  overlays graphics laid over the picture's corners by whoever edited the video (a scoreboard, a timer): outlines
           identical in two pictures of different scenes can only be laid on top; find_overlays keeps one only if
           it's either fully on screen or gone (never half there), with the seconds it's on
  map      whether the minimap is really in its corner (mostly grey, mid-bright, thin road lines): an edited video puts a
           facecam or a real-life shot there, and then the Short shows no minimap (pipeline/game_hud.py)
Sound: FFmpeg's EBU R128 momentary loudness, per second. Words: the game's keywords in the transcript, per second.

Nothing here reads a whole stream into memory, and every FFmpeg runs without a terminal (gotcha 36).
"""
import json
import re
import subprocess
from pathlib import Path

from pipeline.ffmpeg import ffmpeg_exe

GAMES_DIR = Path(__file__).with_name("games")
CHUNK = 300.0   # seconds of stream per FFmpeg run
KEY_GAP = 2.6   # keyframes further apart than this: read one picture a second instead
W, H = 320, 180
POLICE_WINDOW = 6  # seconds either side in which the minimap's red and blue are looked for together


def games():
    """The games Game Mode knows: {"gta5": "GTA V", ...}."""
    out = {}
    for f in sorted(GAMES_DIR.glob("*.json")):
        try:
            out[f.stem] = json.loads(f.read_text(encoding="utf-8")).get("name", f.stem)
        except (OSError, ValueError):
            continue
    return out


def load_game(name):
    """A game's settings (pipeline/games/<name>.json). RuntimeError for a game Pit Crew doesn't know."""
    if not re.fullmatch(r"[a-z0-9_]{1,30}", name or "") or not (GAMES_DIR / f"{name}.json").exists():
        raise RuntimeError("Pit Crew doesn't know that game yet. Choose GTA V, or make Shorts as a normal video.")
    return json.loads((GAMES_DIR / f"{name}.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- FFmpeg, stoppable ---------------------------------

def _ffmpeg(cmd, timeout=1800):
    """(stdout bytes, stderr bytes, return code) of an FFmpeg run that Pause / Stop end within 0.2 s: the check set by
    pipeline.ffmpeg.watching() (web/pause.py Run.doing) is called while it runs, and FFmpeg is killed if it raises.
    Output goes to temporary files, so a full pipe can never hold FFmpeg up."""
    import tempfile
    import time
    from pipeline.ffmpeg import _WATCH
    check = getattr(_WATCH, "check", None)
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=out, stderr=err)
        until = time.time() + timeout
        try:
            while p.poll() is None:
                if check:
                    check()
                if time.time() > until:
                    raise RuntimeError("Reading this stream took too long. Try a shorter part of it.")
                time.sleep(0.2)
        except BaseException:
            p.kill()
            p.wait()
            raise
        out.seek(0)
        err.seek(0)
        return out.read(), err.read(), p.returncode


# ---------------------------------------------------------------- pictures ------------------------------------------

def _frames(video_path, a, span, keyframes):
    """[(t, rgb picture 320x180)] for a..a+span; t in stream seconds."""
    import numpy as np
    vf = f"scale={W}:{H},showinfo" if keyframes else f"fps=1,scale={W}:{H},showinfo"
    cmd = [ffmpeg_exe(), "-nostdin", "-hide_banner", "-loglevel", "info", *(["-skip_frame", "nokey"] if keyframes else []),
           "-ss", f"{max(0.0, a):.3f}", "-t", f"{span:.3f}", "-i", str(Path(video_path).resolve()),
           "-an", "-sn", "-vf", vf, *(["-vsync", "passthrough"] if keyframes else []),
           "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
    stdout, stderr, code = _ffmpeg(cmd)
    if code != 0:
        raise RuntimeError("Couldn't read the pictures of this stream.\n" + stderr.decode("utf-8", "replace")[-300:])
    size = W * H * 3
    n = len(stdout) // size
    times = [float(x) for x in re.findall(rb"pts_time:\s*(-?[\d.]+)", stderr)]
    if len(times) != n:  # (an FFmpeg that logs differently: spread them evenly)
        times = [span * (k + 0.5) / max(1, n) for k in range(n)]
    pics = np.frombuffer(stdout[:n * size], np.uint8).reshape(n, H, W, 3) if n else np.zeros((0, H, W, 3), np.uint8)
    return [(a + max(0.0, t), pics[k]) for k, t in enumerate(times)]


def _box(region):
    x0, y0, x1, y1 = region
    return int(x0 * W), int(y0 * H), max(int(x0 * W) + 1, int(x1 * W)), max(int(y0 * H) + 1, int(y1 * H))


def _share(hsv, region, ranges):
    """Fraction of the region's pixels inside any of the HSV ranges ([[lo], [hi], [lo], [hi], ...])."""
    import cv2
    import numpy as np
    x0, y0, x1, y1 = _box(region)
    part = hsv[y0:y1, x0:x1]
    mask = np.zeros(part.shape[:2], np.uint8)
    for lo, hi in zip(ranges[0::2], ranges[1::2]):
        mask |= cv2.inRange(part, np.array(lo, np.uint8), np.array(hi, np.uint8))
    return float(mask.mean() / 255.0)


def picture_features(rgb, game, prev=None):
    """One picture's signals (see the top of this file), and the small grey copy to compare the next one with."""
    import cv2
    import numpy as np
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    reg, col = game["regions"], game["colors"]
    grey = cv2.resize(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), (160, 90), interpolation=cv2.INTER_AREA).astype(np.int16)
    f = {"sat": float(hsv[..., 1].mean() / 255.0),
         "red": _share(hsv, reg["minimap"], col["police_red"]), "blue": _share(hsv, reg["minimap"], col["police_blue"]),
         "star": _share(hsv, reg["wanted"], col["star"]),
         "wred": _share(hsv, reg["center"], col["wasted_red"]), "gold": _share(hsv, reg["center"], col["passed_gold"]),
         "motion": 0.0, "x": None}
    small = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    lines = cv2.Canny(small, 60, 150) > 0
    f["edges"] = float(lines.mean())  # the pause map: thin lines everywhere
    f["_lines"] = np.packbits(lines)  # for find_overlays() (never saved: per_second drops it)
    f["_small"] = cv2.resize(small, (32, 18), interpolation=cv2.INTER_AREA).astype(np.float32).ravel()  # its scene
    f["bright"] = float(np.percentile(small, 90) / 255.0)  # a black loading screen is grey too
    x0, y0, x1, y1 = _box(reg["minimap"])
    corner, hc = small[y0:y1, x0:x1], hsv[y0:y1, x0:x1]
    th, (lo, hi) = game["thresholds"], game["thresholds"].get("minimap_level", [85, 165])
    f["map"] = float((hc[..., 1] < 60).mean() >= th.get("minimap_grey", 0.6) and lo <= corner.mean() <= hi
                     and (cv2.Canny(corner, 60, 150) > 0).mean() >= th.get("minimap_lines", 0.1))
    if prev is not None:
        diff = np.abs(grey - prev)
        f["motion"] = float(diff.mean() / 255.0)
        cols = diff.sum(axis=0).astype(np.float64)
        if cols.sum() > 0:
            f["x"] = float((cols * (np.arange(cols.size) + 0.5)).sum() / cols.sum() / cols.size)
    return f, grey


def scan_pictures(video_path, a, b, game, prev=None):
    """Signals of every picture read in a..b: ([{"t", ...features}], last grey copy). Keyframes if they're close
    enough, else one picture a second."""
    span = max(0.1, b - a)
    got = _frames(video_path, a, span, keyframes=True)
    if span > 10 and len(got) < span / KEY_GAP:  # keyframes too far apart (or none): one a second
        got = _frames(video_path, a, span, keyframes=False)
    out = []
    for t, rgb in got:
        f, prev = picture_features(rgb, game, prev)
        out.append({"t": round(t, 2), **f})
    return out, prev


# ---------------------------------------------------------------- sound and words ----------------------------------

def loudness(video_path, a, b):
    """{second: loudest momentary loudness in LUFS} for a..b (stream seconds). Silence or no sound = {}."""
    _, stderr, _ = _ffmpeg([ffmpeg_exe(), "-nostdin", "-hide_banner", "-loglevel", "verbose", "-ss", f"{max(0.0, a):.3f}",
                            "-t", f"{max(0.1, b - a):.3f}", "-i", str(Path(video_path).resolve()), "-vn", "-sn",
                            "-af", "ebur128=framelog=verbose", "-f", "null", "-"])
    out = {}
    for t, m in re.findall(rb"t:\s*([\d.]+)\s+TARGET:[^M]*M:\s*(-?[\d.]+|-inf)", stderr):
        if m == b"-inf":
            continue
        s = int(a + float(t))
        out[s] = max(out.get(s, -120.0), float(m))
    return out


def keyword_hits(words, keywords):
    """{second: how many of the game's keywords start in it} from a transcript's words."""
    if not words or not keywords:
        return {}
    norm = [re.sub(r"[^a-z0-9' ]", "", w["w"].lower()).strip() for w in words]
    out = {}
    for k in range(len(words)):
        for kw in keywords:
            parts = kw.split()
            if norm[k:k + len(parts)] == parts:
                s = int(words[k]["s"])
                out[s] = out.get(s, 0) + 1
    return out


# ---------------------------------------------------------------- per second ---------------------------------------

def per_second(pictures, loud, hits, duration, game):
    """Every second's raw signals as lists (index = second): what game_moments scores."""
    n = max(1, int(duration) + 1)
    th = game["thresholds"]
    bins = [[] for _ in range(n)]
    for f in pictures:
        bins[min(n - 1, max(0, int(f["t"])))].append(f)
    # seconds with no picture (keyframes every 2 s) take the nearest picture's values
    filled, last = [], None
    for k in range(n):
        if bins[k]:
            last = k
        filled.append(last)
    nxt = None
    for k in range(n - 1, -1, -1):
        if bins[k]:
            nxt = k
        if not bins[k]:
            cands = [j for j in (filled[k], nxt) if j is not None]
            filled[k] = min(cands, key=lambda j: abs(j - k)) if cands else None
        else:
            filled[k] = k

    def agg(key, fn=max, default=0.0):
        return [fn([f[key] for f in bins[j]]) if j is not None and bins[j] else default for j in filled]

    sat = agg("sat", lambda v: sum(v) / len(v), 0.5)
    sat_med = sorted(sat)[len(sat) // 2] if sat else 0.5
    red, blue, star = agg("red"), agg("blue"), agg("star")
    # the minimap always has some red and blue (water, blips): only what's above this stream's usual level counts
    red_usual, blue_usual = _median([f["red"] for f in pictures]), _median([f["blue"] for f in pictures])
    red = [max(0.0, x - red_usual) for x in red]
    blue = [max(0.0, x - blue_usual) for x in blue]
    out = {
        "motion": agg("motion"),
        "cuts": [1.0 if m > 0.22 else 0.0 for m in agg("motion")],
        # both colours within POLICE_WINDOW s (keyframes 2 s apart can land on the same colour of the flashing); one
        # colour alone counts half (a mission's red blips look like it)
        "police": [min(r, b) if min(r, b) > 0 else max(r, b) / 2
                   for r, b in zip(_window_max(red, POLICE_WINDOW), _window_max(blue, POLICE_WINDOW))],
        "stars": star,
        "grey": [1.0 if s < th["grey_screen"] * sat_med else 0.0 for s in sat],
        "wred": agg("wred"), "gold": agg("gold"),
        "edges": agg("edges", lambda v: sum(v) / len(v)), "bright": agg("bright", lambda v: sum(v) / len(v), 1.0),
        "map": agg("map", lambda v: sum(v) / len(v)),
        "x": agg("x", lambda v: sorted(x for x in v if x is not None)[len([x for x in v if x is not None]) // 2]
                 if any(x is not None for x in v) else None, None),
        "loud": [loud.get(k) for k in range(n)],
        "keywords": [float(hits.get(k, 0)) for k in range(n)],
        "duration": duration,
    }
    found = find_overlays([p.get("_lines") for p in pictures], [p.get("_small") for p in pictures], game)
    out["overlays"] = [{"box": o["box"], "seen": agg_seen(o["seen"], pictures, bins, filled)} for o in found]
    for p in pictures:
        p.pop("_lines", None)
        p.pop("_small", None)
    return out


def agg_seen(seen, pictures, bins, filled):
    """Per second (0-1): the share of that second's pictures where an overlay was on screen."""
    at = {id(p): v for p, v in zip(pictures, seen)}
    return [round(sum(at.get(id(f), 0.0) for f in bins[j]) / len(bins[j]), 2) if j is not None and bins[j] else 0.0
            for j in filled]


OVERLAY_PAIRS = 6000    # pairs of pictures compared
OVERLAY_TOP = 30        # the best-matching pairs a graphic is looked for in
OVERLAY_GROUP = 10      # a graphic: in at least this many of them, at one place (5 let a wall's tiles through)
OVERLAY_HALF = 0.12     # at most this share of pictures may show it half (a scene's own detail comes and goes)
OVERLAY_ON = 0.75       # on screen: this share of its outlines there
OVERLAY_WIN = (31, 21)  # the window matches are counted in (pixels of the 320 x 180 picture)
OVERLAY_LOOK = 1200     # pictures it's looked for in (evenly spread); then checked in every picture


def find_overlays(lines, smalls, game, seed=0):
    """[{"box": [x0, y0, x1, y1] fractions, "seen": [0/1 per picture]}]: graphics laid over the picture's corners by
    whoever edited the video (see the top of this file), never the minimap (game_hud shows that by its own check).

    1. Pairs of pictures from different scenes (far apart in time, different overall look): the corner outlines both
       have, counted in a small window. Busy video matches a lot by chance (median ~50 in a window); a graphic over
       both gives the best matches (~170+).
    2. The OVERLAY_TOP best pairs, grouped by where their window is; a group of OVERLAY_GROUP+ = a candidate, its
       template = the outlines most of the group share.
    3. Kept only if every picture has nearly all of the template or almost none (OVERLAY_HALF): a real graphic is
       either there or not; a scene's own lines (a ring light the video keeps cutting back to) come and go by halves.
    lines: each picture's packed outlines (W x H); smalls: each a 32 x 18 grey copy. Missing ones are None."""
    import cv2
    import numpy as np
    every = [k for k, (a, b) in enumerate(zip(lines, smalls)) if a is not None and b is not None]
    if len(every) < 30:
        return []
    have = every[:: max(1, -(-len(every) // OVERLAY_LOOK))]  # (memory: a 3-hour stream has ~10,000 pictures)
    E = np.array([np.unpackbits(lines[k])[:W * H].reshape(H, W) for k in have], dtype=bool)
    G = np.array([smalls[k] for k in have], dtype=np.float32)
    corner = np.zeros((H, W), bool)
    corner[: int(H * 0.42), :] = True
    corner[int(H * 0.58):, :] = True
    corner[:, int(W * 0.3): int(W * 0.7)] = False
    rng = np.random.default_rng(seed)
    n, best = len(E), []
    gap = max(5, n // 60)
    for _ in range(OVERLAY_PAIRS):
        i, j = (int(v) for v in rng.integers(0, n, 2))
        if abs(i - j) < gap or float(np.abs(G[i] - G[j]).mean()) < 25:  # the same scene
            continue
        cnt = cv2.boxFilter((E[i] & E[j] & corner).astype(np.float32), -1, OVERLAY_WIN, normalize=False)
        y, x = np.unravel_index(int(cnt.argmax()), cnt.shape)
        best.append((float(cnt.max()), i, j, int(y), int(x)))
    best.sort(reverse=True)
    groups = []
    for _, i, j, y, x in best[:OVERLAY_TOP]:
        g = next((g for g in groups if abs(g["y"] - y) <= 12 and abs(g["x"] - x) <= 16), None)
        if g is None:
            groups.append({"y": y, "x": x, "pairs": [(i, j)]})
        else:
            g["pairs"].append((i, j))
    mm = _box(game["regions"]["minimap"])
    out = []
    for g in groups:
        if len(g["pairs"]) < OVERLAY_GROUP:
            continue
        win = np.zeros((H, W), bool)
        win[max(0, g["y"] - 25): g["y"] + 26, max(0, g["x"] - 35): g["x"] + 36] = True
        shared = np.array([E[i] & E[j] & win for i, j in g["pairs"]]).mean(axis=0)
        tpl = shared >= 0.5
        if tpl.sum() < 25:
            continue
        share = E[:, tpl].mean(axis=1)
        on = share > OVERLAY_ON
        if 1 - (share < 0.25).mean() - on.mean() > OVERLAY_HALF or on.mean() < 0.02:
            continue
        # its extent: what's an outline in most pictures it's on, near the template (a score's other rows too)
        near = np.zeros((H, W), bool)
        ty, tx = np.nonzero(tpl)
        near[max(0, ty.min() - 20): ty.max() + 21, max(0, tx.min() - 20): tx.max() + 21] = True
        ys, xs = np.nonzero((E[on].mean(axis=0) >= 0.6) & near & corner)
        x0, y0, x1, y1 = max(0, xs.min() - 3), max(0, ys.min() - 3), min(W, xs.max() + 4), min(H, ys.max() + 4)
        ix = max(0, min(x1, mm[2]) - max(x0, mm[0])) * max(0, min(y1, mm[3]) - max(y0, mm[1]))
        if ix > 0.3 * (x1 - x0) * (y1 - y0):  # the minimap
            continue
        flat = tpl.ravel()
        per = [0.0] * len(lines)
        for k in every:  # every picture, one at a time
            per[k] = float(np.unpackbits(lines[k])[:W * H][flat].mean() > OVERLAY_ON)
        out.append({"box": [round(x0 / W, 4), round(y0 / H, 4), round(x1 / W, 4), round(y1 / H, 4)], "seen": per})
    return out


def _median(v):
    v = sorted(v)
    return v[len(v) // 2] if v else 0.0


def _window_max(v, r):
    return [max(v[max(0, k - r):k + r + 1]) for k in range(len(v))]
