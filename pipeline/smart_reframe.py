"""
Smart Reframe (the editor's Reframe tool, web/reframe.py): what of the wide vlog the 9:16 Short shows, saved on the Short
as moment["reframe"]. None (every Short made before, and every new one) = the crop around the face found when it was
made (pipeline/reframe.py crop_filter(meta, cx)), exactly as before.

    {"layout": "fill" | "fit" | "split",
     "moves": [{"t": vlog seconds, "x": 0-1, "y": 0-1, "z": 1-ZOOM_MAX,      fill: where the frame is from time t on
                "jump": true (this one: no glide to it)}, ...],
     "cut": false,                                                               fill: every move jumps instead of gliding
     "shots": [{"t": vlog seconds, "fit": true | false}, ...],                   fill: Auto layout per shot: from t on, the
                                                                                 whole picture (Fit) or the frame (Fill)
     "punch": {"amount": 0-PUNCH_MAX, "at": [vlog seconds, ...]},                fill: zoom in at one, out at the next...
     "top": {"x", "y", "z"}, "bottom": {"x", "y", "z"}}                          split: the two views, stacked

x / y are the middle of the frame as a fraction of the vlog's picture; z = how far in (1 = the full height). Times are the
vlog's seconds, like pieces and caption edits, so cuts and trims never move them. Fill with one move = one fixed frame;
with more, the frame glides (GLIDE s, eased) to each move's place, arriving at its time. Fit = the whole picture across
the Short over a blurred copy of itself. Split = two 9:8 views stacked (two people, a face and what they show).
Smart framing (auto_shots, track_moves, the page's punch-ins) only ever writes these settings: the creator can change
everything they made. Fill with shots draws both the frame and Fit and shows Fit over it in the Fit shots
(overlay enable=, on the Short's clock).

Moving frames are drawn with FFmpeg's sendcmd: a command file (written next to the .ass, deleted after) sets the crop's
x / y, and the scale's size when the zoom changes, every 1/30 s. A crop's own size can't change mid-run (FFmpeg stops
after the first frame), so a zoom is a fixed crop (the widest frame) then a scale to the size that makes the wanted part
fill 1080x1920, then a crop of that (gotcha 34).
"""
import math
import statistics
import uuid
from pathlib import Path

from pipeline.constants import OUT_H, OUT_W
from pipeline.reframe import crop_filter

LAYOUTS = ("fill", "fit", "split")
ZOOM_MAX = 2.5
MAX_MOVES = 80
GLIDE = 0.6      # seconds a glide takes to reach a move
STEP = 1 / 30    # how often a moving frame is set (the Shorts are 30 fps)
SPLIT_H = OUT_H // 2  # each view of a split
FACE_EVERY = 0.5      # seconds between looks for the face (Follow the speaker)
DEAD = 0.07           # the face may drift this much (of the picture's width) before the frame follows
HOLD = 1.0            # seconds it must stay away before a move is added
MAX_SHOTS = 120
PUNCH_MAX = 0.3       # a punch-in zooms at most 30 % further in
MAX_PUNCH = 200
SCENE = 0.32          # FFmpeg's scene score over which a frame starts a new shot
MIN_SHOT = 1.0        # seconds: a shot shorter than this joins the one before
TRACK_EVERY = 0.2     # seconds between tracked frames (Tap to track)


def _num(v, lo, hi, default):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    return default if v != v else min(hi, max(lo, v))


def _view(v, default):
    v = v if isinstance(v, dict) else {}
    return {"x": round(_num(v.get("x"), 0, 1, default["x"]), 4), "y": round(_num(v.get("y"), 0, 1, default["y"]), 4),
            "z": round(_num(v.get("z"), 1, ZOOM_MAX, default["z"]), 3)}


SPLIT_TOP, SPLIT_BOTTOM = {"x": 0.3, "y": 0.5, "z": 1.0}, {"x": 0.7, "y": 0.5, "z": 1.0}


def clean_reframe(r, duration=None):
    """Checked reframe settings (known layout, numbers in range, moves in time order inside the vlog), or None for
    the default framing."""
    if not isinstance(r, dict):
        return None
    layout = r.get("layout") if r.get("layout") in LAYOUTS else "fill"
    top = duration if duration and duration > 0 else 1e9
    moves = {}
    for m in (r.get("moves") if isinstance(r.get("moves"), list) else [])[:MAX_MOVES * 2]:
        if not isinstance(m, dict):
            continue
        t = round(_num(m.get("t"), 0, top, -1), 2)
        if t < 0:
            continue
        moves[t] = {"t": t, **_view(m, {"x": 0.5, "y": 0.5, "z": 1.0}), **({"jump": True} if m.get("jump") else {})}
    moves = sorted(moves.values(), key=lambda m: m["t"])[:MAX_MOVES]  # (the same time twice: the last one)
    out = {"layout": layout, "moves": moves, "cut": bool(r.get("cut"))}
    if layout == "split":
        out["top"], out["bottom"] = _view(r.get("top"), SPLIT_TOP), _view(r.get("bottom"), SPLIT_BOTTOM)
    if layout == "fill":
        shots = {}
        for x in (r.get("shots") if isinstance(r.get("shots"), list) else [])[:MAX_SHOTS * 2]:
            t = round(_num(x.get("t"), 0, top, -1), 2) if isinstance(x, dict) else -1
            if t >= 0:
                shots[t] = {"t": t, "fit": bool(x.get("fit"))}
        shots = sorted(shots.values(), key=lambda x: x["t"])[:MAX_SHOTS]
        if any(x["fit"] for x in shots):
            out["shots"] = shots
        p = r.get("punch") if isinstance(r.get("punch"), dict) else {}
        amount = round(_num(p.get("amount"), 0, PUNCH_MAX, 0), 3)
        at = sorted({round(_num(t, 0, top, -1), 2) for t in (p.get("at") if isinstance(p.get("at"), list) else [])[:MAX_PUNCH * 2]} - {-1})
        if amount > 0 and at:
            out["punch"] = {"amount": amount, "at": at[:MAX_PUNCH]}
        if not moves and "shots" not in out and "punch" not in out:
            return None
    return out


def reframe_style_only(r):
    """For Try again (a new moment): the layout and the split views stay, the moves (on the old moment's times) go."""
    r = clean_reframe(r)
    if not r:
        return None
    return clean_reframe({k: v for k, v in r.items() if k not in ("shots", "punch")} | {"moves": []})


def vertical(meta):
    return meta["width"] / meta["height"] <= 9 / 16 + 0.01


def _ease(f):
    return f * f * (3 - 2 * f)


def framing_at(moves, t, cut=False):
    """(x, y, z) of the frame at vlog time t: the last move's place, gliding to the next one in the GLIDE s before it."""
    if not moves:
        return 0.5, 0.5, 1.0
    k = 0
    while k + 1 < len(moves) and moves[k + 1]["t"] <= t:
        k += 1
    cur = moves[k]
    if t < moves[0]["t"]:
        return moves[0]["x"], moves[0]["y"], moves[0]["z"]
    nxt = moves[k + 1] if k + 1 < len(moves) else None
    if cut or not nxt or nxt.get("jump"):
        return cur["x"], cur["y"], cur["z"]
    start = max(cur["t"], nxt["t"] - GLIDE)
    if t <= start:
        return cur["x"], cur["y"], cur["z"]
    f = _ease((t - start) / max(1e-6, nxt["t"] - start))
    return tuple(cur[k2] + (nxt[k2] - cur[k2]) * f for k2 in ("x", "y", "z"))


def punch_at(punch, t):
    """How much further in a punch-in makes the frame at vlog time t: in at the first, out at the next, in again..."""
    if not punch:
        return 1.0
    n = sum(1 for p in punch["at"] if p <= t)
    return 1.0 + punch["amount"] if n % 2 else 1.0


def fit_at(shots, t):
    """Whether the Fit shot (the whole picture) is showing at vlog time t."""
    cur = None
    for x in shots or []:
        if x["t"] <= t:
            cur = x
    return bool(cur and cur["fit"])


def fit_ranges(shots, pieces):
    """The Short-clock (start, end) stretches where a Fit shot shows."""
    if not shots:
        return []
    out, done = [], 0.0
    for a, b in pieces:
        for k, x in enumerate(shots):
            if not x["fit"]:
                continue
            s0, s1 = x["t"], shots[k + 1]["t"] if k + 1 < len(shots) else 1e12
            lo, hi = max(a, s0), min(b, s1)
            if hi > lo + 1e-3:
                out.append((done + lo - a, done + hi - a))
        done += b - a
    merged = []
    for lo, hi in sorted(out):
        if merged and lo <= merged[-1][1] + 1e-3:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    return merged


def to_vlog(pieces, t):
    """A time on the Short's clock as the vlog's seconds."""
    done = 0.0
    for a, b in pieces:
        if t <= done + (b - a):
            return a + (t - done)
        done += b - a
    return pieces[-1][1]


def _even(v):
    return int(round(v / 2)) * 2


def _up(v):
    """Up to an even number (a hair under one counts as one)."""
    return int(math.ceil(v / 2 - 1e-6)) * 2


def window(meta, x, y, z, aspect=9 / 16):
    """The part of the vlog's picture a frame shows: (left, top, width, height) in its pixels, inside the picture."""
    w, h = meta["width"], meta["height"]
    ch = h / z
    cw = ch * aspect
    if cw > w:
        cw, ch = w / z, w / z / aspect
    left = min(max(x * w - cw / 2, 0), w - cw)
    top = min(max(y * h - ch / 2, 0), h - ch)
    return left, top, cw, ch


def _crop(meta, v, aspect, out_w, out_h):
    left, top, cw, ch = window(meta, v["x"], v["y"], v["z"], aspect)
    cw, ch = min(_even(cw), meta["width"] // 2 * 2), min(_even(ch), meta["height"] // 2 * 2)
    left = min(_even(left), meta["width"] - cw)
    top = min(_even(top), meta["height"] - ch)
    return f"crop={cw}:{ch}:{left}:{top},scale={out_w}:{out_h}:flags=lanczos"


def reframe_filter(meta, cx, r, pieces, job_dir):
    """(filter chain for the Short's picture on its own clock, name of a command file written in job_dir or None).
    No settings = crop_filter(meta, cx), exactly. Delete the file after the FFmpeg run (drop_commands)."""
    r = clean_reframe(r)
    if not r or vertical(meta):
        return crop_filter(meta, cx), None
    if r["layout"] == "fit":
        return _fit(), None
    if r["layout"] == "split":
        a = 9 / 8  # each view: 1080 x 960
        return (f"split[rfa][rfb];[rfa]{_crop(meta, r['top'], a, OUT_W, SPLIT_H)}[rft];"
                f"[rfb]{_crop(meta, r['bottom'], a, OUT_W, SPLIT_H)}[rfu];[rft][rfu]vstack,setsar=1"), None
    # Fill: the frame (no moves = the one around the face it was made with), punch-ins, and Fit over it in Fit shots
    moves = r["moves"] or [{"t": 0.0, "x": (cx if isinstance(cx, (int, float)) else meta["width"] / 2) / meta["width"],
                            "y": 0.5, "z": 1.0}]
    punch = r.get("punch")
    if len(moves) == 1 and not punch:
        fill, name = _crop(meta, moves[0], 9 / 16, OUT_W, OUT_H), None
    else:
        fill, name = _moving(meta, moves, r["cut"], pieces, Path(job_dir), punch)
    fits = fit_ranges(r.get("shots"), pieces)
    if not fits:
        return fill, name
    on = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in fits)
    return f"split[rfm][rfn];[rfm]{fill}[rff];[rfn]{_fit()}[rft];[rff][rft]overlay=enable='{on}',setsar=1", name


def _fit():
    """The whole picture across the Short, over a blurred, darker copy filling the rest (blurred small: cheaper)."""
    return (f"split[rfx][rfy];[rfx]scale={OUT_W // 4}:{OUT_H // 4}:force_original_aspect_ratio=increase,"
            f"crop={OUT_W // 4}:{OUT_H // 4},boxblur=8:2,eq=brightness=-0.08,scale={OUT_W}:{OUT_H}[rfbg];"
            f"[rfy]scale={OUT_W}:-2:flags=lanczos[rffg];[rfbg][rffg]overlay=(W-w)/2:(H-h)/2,setsar=1")


def _moving(meta, moves, cut, pieces, job_dir, punch=None):
    w, h = meta["width"], meta["height"]
    total = sum(b - a for a, b in pieces)
    zmin = min(m["z"] for m in moves)
    zoom = bool(punch) or any(abs(m["z"] - zmin) > 1e-3 for m in moves)  # (a punch-in only ever zooms further in)
    # the widest frame: a fixed crop that every frame fits inside (moved along); with a zoom, scaled and cropped again
    _, _, ww, wh = window(meta, 0.5, 0.5, zmin)
    ww, wh = min(_even(ww), w // 2 * 2), min(_even(wh), h // 2 * 2)
    lines, last, n = [], None, 0
    while n * STEP <= total + STEP:
        t = n * STEP
        tv = to_vlog(pieces, min(t, total))
        x, y, z = framing_at(moves, tv, cut)
        left, top, cw, ch = window(meta, x, y, min(ZOOM_MAX * (1 + PUNCH_MAX), z * punch_at(punch, tv)))
        ax = min(max(left + cw / 2 - ww / 2, 0), w - ww)  # the widest frame around this one
        ay = min(max(top + ch / 2 - wh / 2, 0), h - wh)
        if zoom:
            # the scaled size rounded up (never under 1080x1920: on 640x360 or 1280x720 rounding down left it 2 px short),
            # the crop inside it
            s = OUT_H / ch
            sw, sh = max(OUT_W, _up(ww * s)), max(OUT_H, _up(wh * s))
            vals = (_even(ax), _even(ay), sw, sh,
                    min(max(0, _even((left - _even(ax)) * s)), sw - OUT_W), min(max(0, _even((top - _even(ay)) * s)), sh - OUT_H))
        else:
            vals = (_even(ax), _even(ay))
        if vals != last:
            cmd = f"[enter] crop@rfa x {vals[0]}, [enter] crop@rfa y {vals[1]}"
            if zoom:
                cmd += (f", [enter] scale@rfz w {vals[2]}, [enter] scale@rfz h {vals[3]}"
                        f", [enter] crop@rf x {vals[4]}, [enter] crop@rf y {vals[5]}")
            lines.append(f"{t:.4f} {cmd};")
            last = vals
        n += 1
    name = f"reframe_{uuid.uuid4().hex[:10]}.cmd"
    (job_dir / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
    if zoom:
        return (f"sendcmd=f={name},crop@rfa={ww}:{wh}:0:0,scale@rfz=w={OUT_W}:h={OUT_H}:flags=bicubic,"
                f"crop@rf={OUT_W}:{OUT_H}:0:0,setsar=1"), name
    return f"sendcmd=f={name},crop@rfa={ww}:{wh}:0:0,scale={OUT_W}:{OUT_H}:flags=lanczos", name


def drop_commands(job_dir, name):
    if name:
        (Path(job_dir) / name).unlink(missing_ok=True)


def follow_moves(video_path, meta, pieces, z=1.0, offset=0.0):
    """Follow the speaker: moves that keep the main face in the frame (a new one only when the face has moved DEAD of
    the picture for HOLD s). [] when no face is found (or face finding isn't available): never an error."""
    try:
        return _follow(video_path, meta, pieces, z, offset)
    except Exception as e:  # noqa: BLE001
        print(f"Follow the speaker skipped ({e}).")
        return []


def _faces(video_path, pieces, offset=0.0):
    """[(vlog time, x 0-1, y 0-1)] of the biggest face, every FACE_EVERY s inside the pieces (read in order)."""
    import cv2
    if not hasattr(cv2, "CascadeClassifier"):
        return []
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    out = []
    try:
        for a, b in pieces:
            cap.set(cv2.CAP_PROP_POS_MSEC, (a - offset) * 1000)  # one seek per piece, then read on (vlog times kept)
            t, nxt = a, a
            while t <= b:
                ok = cap.grab()
                if not ok:
                    break
                if t >= nxt:
                    ok, frame = cap.retrieve()
                    nxt += FACE_EVERY
                    if ok:
                        H, W = frame.shape[:2]
                        sc = 640 / W
                        gray = cv2.cvtColor(cv2.resize(frame, None, fx=sc, fy=sc), cv2.COLOR_BGR2GRAY)
                        faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(36, 36))
                        if len(faces):
                            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
                            out.append((t, float((x + w / 2) / sc / W), float((y + h / 2) / sc / H)))
                t += 1 / fps
    finally:
        cap.release()
    return out


def _follow(video_path, meta, pieces, z, offset=0.0):
    if vertical(meta):
        return []
    seen = _faces(video_path, pieces, offset)
    if len(seen) < 2:
        return []
    xs = [s[1] for s in seen]
    smooth = [statistics.median(xs[max(0, k - 2):k + 3]) for k in range(len(xs))]  # one wrong face doesn't move it
    y_of = lambda k: min(1.0, seen[k][2] + 0.12 / z) if z > 1 else 0.5  # zoomed in: the face in the upper part
    moves = [{"t": round(pieces[0][0], 2), "x": round(smooth[0], 4), "y": round(y_of(0), 4), "z": z}]
    k = 1
    while k < len(seen):
        if abs(smooth[k] - moves[-1]["x"]) > DEAD:
            later = [j for j in range(k, len(seen)) if seen[j][0] - seen[k][0] <= HOLD]
            if all(abs(smooth[j] - moves[-1]["x"]) > DEAD for j in later) and seen[later[-1]][0] - seen[k][0] >= HOLD - FACE_EVERY:
                x = statistics.median(smooth[j] for j in later)
                moves.append({"t": round(seen[k][0], 2), "x": round(x, 4), "y": round(y_of(k), 4), "z": z})
                k = later[-1] + 1
                continue
        k += 1
    return moves[:MAX_MOVES]


# ---- Auto layout per shot: where the vlog cuts to another shot, and whether each shot has someone to frame
def auto_shots(video_path, meta, pieces, offset=0.0):
    """{"shots": [{"t", "fit"}], "moves": [{"t", "x", "y", "z", "jump"}]}: a new shot at each scene change inside the
    kept parts; a shot with a clear face is framed on it (Fill), one without (a view, food, a sign) shows whole (Fit).
    Never an error: no faces anywhere = every shot Fit; nothing readable = {} ."""
    try:
        return _auto_shots(video_path, meta, pieces, offset)
    except Exception as e:  # noqa: BLE001
        print(f"Auto layout skipped ({e}).")
        return {}


def scene_changes(video_path, a, b, offset=0.0):
    """Vlog seconds inside a..b where FFmpeg sees a new shot (scene score over SCENE), on a small copy (quick)."""
    import re
    import subprocess
    from pipeline.ffmpeg import ffmpeg_exe
    p = subprocess.run([ffmpeg_exe(), "-hide_banner", "-ss", f"{max(0.0, a - offset):.3f}", "-i", str(Path(video_path).resolve()),
                        "-t", f"{b - a:.3f}", "-an", "-vf", f"scale=320:-2,select='gt(scene\\,{SCENE})',showinfo", "-f", "null", "-"],
                       capture_output=True, text=True)
    return [round(a + float(t), 3) for t in re.findall(r"pts_time:([0-9.]+)", p.stderr)]


def _auto_shots(video_path, meta, pieces, offset):
    if vertical(meta):
        return {}
    starts = []
    for a, b in pieces:
        starts.append(a)
        for t in scene_changes(video_path, a, b, offset):
            if t - starts[-1] >= MIN_SHOT and b - t >= MIN_SHOT * 0.5:
                starts.append(t)
    ends = starts[1:] + [pieces[-1][1]]
    import cv2
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    cap = cv2.VideoCapture(str(video_path))
    shots, moves = [], []
    try:
        for s, e in zip(starts, ends):
            xs = []
            for f in (0.2, 0.5, 0.8):  # three looks inside the shot
                cap.set(cv2.CAP_PROP_POS_MSEC, (s + (e - s) * f - offset) * 1000)
                ok, frame = cap.read()
                if not ok:
                    continue
                H, W = frame.shape[:2]
                sc = 640 / W
                gray = cv2.cvtColor(cv2.resize(frame, None, fx=sc, fy=sc), cv2.COLOR_BGR2GRAY)
                faces = [f2 for f2 in cascade.detectMultiScale(gray, 1.1, 5, minSize=(30, 30)) if f2[3] / sc >= H * 0.07]
                if faces:
                    x, y, w, h = max(faces, key=lambda f2: f2[2] * f2[3])
                    xs.append(float((x + w / 2) / sc / W))
            fit = not xs
            shots.append({"t": round(s, 2), "fit": fit})
            if not fit:
                moves.append({"t": round(s, 2), "x": round(statistics.median(xs), 4), "y": 0.5, "z": 1.0, "jump": True})
    finally:
        cap.release()
    return {"shots": shots[:MAX_SHOTS], "moves": moves[:MAX_MOVES]}


# ---- Tap to track: the frame follows what the creator clicked on, as long as it can be seen
def track_moves(video_path, meta, pieces, at, x, y, z=1.0, offset=0.0, seconds=60.0):
    """(moves, until): from vlog time `at`, moves that keep what's at (x, y) (fractions of the picture) in the frame,
    every 0.5 s, smoothed; until = where it was lost (or its part ends). ([], at) when it can't follow it."""
    try:
        return _track(video_path, meta, pieces, at, x, y, z, offset, seconds)
    except Exception as e:  # noqa: BLE001
        print(f"Tap to track skipped ({e}).")
        return [], at


def _track(video_path, meta, pieces, at, x, y, z, offset, seconds):
    import cv2
    piece = next(((a, b) for a, b in pieces if a <= at < b), None)
    if not piece or vertical(meta):
        return [], at
    end = min(piece[1], at + seconds)  # a cut to another part means another place: stop there
    cap = cv2.VideoCapture(str(video_path))
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        cap.set(cv2.CAP_PROP_POS_MSEC, (at - offset) * 1000)
        ok, frame = cap.read()
        if not ok:
            return [], at
        H, W = frame.shape[:2]
        sc = min(1.0, 320 / W)
        small = lambda f: cv2.resize(f, None, fx=sc, fy=sc) if sc < 1 else f
        # what was clicked: a patch around it, looked for again near where it was last (template matching on a small
        # grey copy: ~1 ms a look); the patch slowly takes in how it changes; lost when it no longer matches well
        gray = lambda f: cv2.cvtColor(small(f), cv2.COLOR_BGR2GRAY)
        g0 = gray(frame)
        gh, gw = g0.shape
        side = max(16, int(H * sc * 0.16)) // 2 * 2
        cx0, cy0 = x * gw, y * gh
        x0, y0 = int(min(max(0, cx0 - side / 2), gw - side)), int(min(max(0, cy0 - side / 2), gh - side))
        tmpl = g0[y0:y0 + side, x0:x0 + side].astype("float32")
        px, py = x0, y0
        seen, t, every = [(at, x, y)], at, max(1, round(fps * TRACK_EVERY))
        n = 0
        while t < end:
            ok = cap.grab()
            if not ok:
                break
            n += 1
            t = at + n / fps
            if n % every:
                continue
            ok, frame = cap.retrieve()
            if not ok:
                break
            g = gray(frame)
            r = side  # search this far around the last place
            sx0, sy0 = max(0, px - r), max(0, py - r)
            sx1, sy1 = min(gw, px + side + r), min(gh, py + side + r)
            area = g[sy0:sy1, sx0:sx1].astype("float32")
            if area.shape[0] < side or area.shape[1] < side:
                break
            res = cv2.matchTemplate(area, tmpl, cv2.TM_CCOEFF_NORMED)
            _, score, _, (mx, my) = cv2.minMaxLoc(res)
            if score < 0.45:
                break
            px, py = sx0 + mx, sy0 + my
            tmpl = cv2.addWeighted(tmpl, 0.85, g[py:py + side, px:px + side].astype("float32"), 0.15, 0)
            seen.append((t, (px + side / 2) / gw, (py + side / 2) / gh))
    finally:
        cap.release()
    until = seen[-1][0]
    moves, last = [], None
    for k in range(0, len(seen), 3):  # every 0.6 s: the middle of what it saw in the second around then (steadier)
        near = seen[max(0, k - 2):k + 3]
        mx, my = statistics.median(s[1] for s in near), statistics.median(s[2] for s in near)
        if last and abs(mx - last[0]) < 0.03 and abs(my - last[1]) < 0.03:  # small shifts: the frame stays put
            continue
        moves.append({"t": round(seen[k][0], 2), "x": round(mx, 4), "y": round(my if z > 1 else 0.5, 4), "z": round(z, 2)})
        last = (mx, my)
    return moves[:MAX_MOVES], round(until, 2)
