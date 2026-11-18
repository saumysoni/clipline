"""
Game Mode, step 4: how each gameplay Short is framed, written as ordinary Reframe settings (moment["reframe"],
pipeline/smart_reframe.py, gotcha 34), so the creator can change all of it in the editor's Reframe tool.

- A facecam (the streamer's camera in a corner) is looked for once per stream: a face found in the same small spot in
  most of FACECAM_LOOKS pictures spread over the stream. Found = **Split**: the game on top, the facecam below.
  The bottom view's zoom is capped at smart_reframe.ZOOM_MAX (2.5), so a small facecam shows with some game around
  it: drag / zoom it in Reframe (stage 2 of gaming.md brings a facecam box of its own).
- No facecam = **Fill that changes through the Short** (auto_frame): a new frame at every cut (FFmpeg's scene changes),
  and inside each shot it follows the person on screen (faces every LOOK_EVERY s, moving only when they've moved DEAD
  for HOLD s); two people too far apart for a 9:16 frame (a streamer talking about their character beside it) = that
  shot shows whole (Fit); no one = the frame sits on the motion. Edited compilations (facecams, real-life cameras and
  gameplay cut together) need this: one fixed frame lost whoever spoke after each cut. If reading the video fails,
  one frame per part on the motion (framing()).

No web code here.
"""
import statistics

from pipeline.reframe import key_frames
from pipeline.smart_reframe import DEAD, HOLD, MAX_MOVES, MAX_SHOTS, MIN_SHOT, ZOOM_MAX, scene_changes

FACECAM_LOOKS = 12     # pictures looked at for a facecam
FACECAM_SHARE = 0.4    # in at least this share of them, in the same spot
LOOK_W = 640
NEAR = 0.06            # two faces closer than this (fraction of the picture) are the same spot
CAM_GROW = (2.6, 2.4)  # a webcam's frame around the face found in it (width, height, times the face's size)
LOOK_EVERY = 0.5       # seconds between looks for people (auto_frame)
MIN_FACE = 0.07        # a face smaller than this (of the picture's height) is background
WIDE = 1.0             # the view's shape (width / height) on Fill game Shorts: a square across the middle, over a
                       # blurred copy, so people and the game look smaller with what's around them (smart_reframe "wide")
APART = 0.4            # in this share of a shot's looks two faces too far apart for one frame = show it whole


def _faces(gray):
    import cv2
    if not hasattr(cv2, "CascadeClassifier"):
        return []
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    h, w = gray.shape[:2]
    found = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(max(16, w // 40),) * 2)
    return [((x + fw / 2) / w, (y + fh / 2) / h, fw / w, fh / h) for x, y, fw, fh in found]


def facecam_spot(faces_per_look):
    """The facecam box {"x0", "y0", "x1", "y1"} (fractions of the picture) from the faces found in each look
    ([[(cx, cy, w, h), ...], ...]), or None. Pure, for tests."""
    looks = [f for f in faces_per_look if f is not None]
    if not looks:
        return None
    spots = []  # [cx, cy, w, h, how many looks]
    for faces in looks:
        seen = set()
        for cx, cy, w, h in faces:
            if w > 0.25:  # a face filling the screen is the game's (a cutscene), not a webcam in a corner
                continue
            k = next((i for i, s in enumerate(spots) if abs(s[0] - cx) < NEAR and abs(s[1] - cy) < NEAR), None)
            if k is None:
                spots.append([cx, cy, w, h, 0])
                k = len(spots) - 1
            if k not in seen:
                spots[k][4] += 1
                seen.add(k)
    best = max(spots, key=lambda s: s[4], default=None)
    if not best or best[4] < max(2, FACECAM_SHARE * len(looks)):
        return None
    cx, cy, w, h, _ = best
    gw, gh = w * CAM_GROW[0] / 2, h * CAM_GROW[1] / 2
    return {"x0": round(max(0.0, cx - gw), 4), "y0": round(max(0.0, cy - gh), 4),
            "x1": round(min(1.0, cx + gw), 4), "y1": round(min(1.0, cy + gh), 4)}


def _one_picture(video_path, t):
    """[one grey picture LOOK_W wide at t] when the stream has no keyframe near t (or [])."""
    import subprocess
    from pathlib import Path

    import cv2
    import numpy as np
    from pipeline.ffmpeg import ffmpeg_exe
    p = subprocess.run([ffmpeg_exe(), "-nostdin", "-hide_banner", "-loglevel", "error", "-ss", f"{t:.2f}",
                        "-i", str(Path(video_path).resolve()), "-frames:v", "1", "-vf", f"scale={LOOK_W}:-2",
                        "-f", "image2pipe", "-c:v", "png", "-"], stdin=subprocess.DEVNULL, capture_output=True, timeout=60)
    if p.returncode or not p.stdout:
        return []
    pic = cv2.imdecode(np.frombuffer(p.stdout, np.uint8), cv2.IMREAD_GRAYSCALE)
    return [pic] if pic is not None else []


def find_facecam(video_path, duration):
    """The stream's facecam box, or None (also when face finding isn't available: it never fails a run)."""
    try:
        looks = []
        for k in range(FACECAM_LOOKS):
            t = duration * (k + 0.5) / FACECAM_LOOKS
            pics = key_frames(video_path, t, min(duration, t + 4), LOOK_W) or _one_picture(video_path, t)
            looks.append(_faces(pics[0]) if pics else None)
        return facecam_spot(looks)
    except Exception as e:  # noqa: BLE001
        print(f"Game Mode: facecam finding skipped ({e}).")
        return None


def action_x(xs, a, b):
    """Where the motion is in a..b (0-1, from game_signals per second "x"), or the middle."""
    got = sorted(x for x in xs[int(a):int(b) + 1] if x is not None)
    return got[len(got) // 2] if got else 0.5


def framing(moment, xs, meta, facecam):
    """(cx in the stream's pixels, Reframe settings) for one gameplay Short."""
    pieces = moment.get("pieces") or [[moment["start"], moment["end"]]]
    w, h = meta["width"], meta["height"]
    first = action_x(xs, *pieces[0])
    if w / h < 1.2:  # an already tall or square video: nothing to crop
        return first * w, None
    if facecam:
        ch = max(0.05, facecam["y1"] - facecam["y0"])
        cw = max(0.05, facecam["x1"] - facecam["x0"])
        z = min(1 / ch, (9 / 8) / (cw * w / h))  # a 9:8 view: as far in as still shows the whole facecam
        bottom = {"x": round((facecam["x0"] + facecam["x1"]) / 2, 4), "y": round((facecam["y0"] + facecam["y1"]) / 2, 4),
                  "z": round(min(ZOOM_MAX, max(1.0, z)), 3)}
        return first * w, {"layout": "split", "moves": [], "cut": False,
                           "top": {"x": round(first, 4), "y": 0.5, "z": 1.0}, "bottom": bottom}
    moves = [{"t": round(a, 2), "x": round(action_x(xs, a, b), 4), "y": 0.5, "z": 1.0, "jump": True} for a, b in pieces]
    return first * w, {"layout": "fill", "moves": moves, "cut": True, "wide": WIDE}


def shot_plan(looks, starts, end, xs, crop_w):
    """Reframe settings {"layout": "fill", "moves", "shots"} for the shots starting at `starts` (vlog seconds, the last
    ends at `end`), from `looks` = [(t, [(cx, cy, w, h), ...]), ...] (faces every LOOK_EVERY s) and the motion's x per
    second `xs`. crop_w: a 9:16 frame's width as a share of the picture. Pure, for tests."""
    ends = starts[1:] + [end]
    moves, shots = [], []
    for s, e in zip(starts, ends):
        mine = [(t, [f for f in fs if f[3] >= MIN_FACE]) for t, fs in looks if s <= t < e]
        with_faces = [(t, fs) for t, fs in mine if fs]
        if mine and len(with_faces) >= max(1, 0.3 * len(mine)):
            apart = sum(1 for _, fs in with_faces if max(f[0] for f in fs) - min(f[0] for f in fs) > crop_w * 0.9)
            if apart >= APART * len(with_faces):
                shots.append({"t": round(s, 2), "fit": True})
                moves.append({"t": round(s, 2), "x": 0.5, "y": 0.5, "z": 1.0, "jump": True})
                continue
            shots.append({"t": round(s, 2), "fit": False})
            seen = [(t, max(fs, key=lambda f: f[2] * f[3])[0]) for t, fs in with_faces]
            smooth = [statistics.median(x for _, x in seen[max(0, k - 2):k + 3]) for k in range(len(seen))]
            moves.append({"t": round(s, 2), "x": round(statistics.median(smooth[:3]), 4), "y": 0.5, "z": 1.0,
                          "jump": True})
            k = 1
            while k < len(seen):  # the person moves: glide after them once they've stayed away HOLD s
                later = [j for j in range(k, len(seen)) if seen[j][0] - seen[k][0] <= HOLD]
                if (all(abs(smooth[j] - moves[-1]["x"]) > DEAD for j in later)
                        and seen[later[-1]][0] - seen[k][0] >= HOLD - LOOK_EVERY):
                    moves.append({"t": round(seen[k][0], 2), "x": round(statistics.median(smooth[j] for j in later), 4),
                                  "y": 0.5, "z": 1.0})
                    k = later[-1] + 1
                    continue
                k += 1
        else:
            shots.append({"t": round(s, 2), "fit": False})
            moves.append({"t": round(s, 2), "x": round(action_x(xs, s, e), 4), "y": 0.5, "z": 1.0, "jump": True})
    out = {"layout": "fill", "moves": moves[:MAX_MOVES], "cut": False, "wide": WIDE}
    if any(x["fit"] for x in shots):
        out["shots"] = shots[:MAX_SHOTS]
    return out


def _looks(video_path, pieces, offset=0.0):
    """[(vlog time, faces)] every LOOK_EVERY s inside the pieces (one seek per piece, then read on)."""
    import cv2
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    out = []
    try:
        for a, b in pieces:
            cap.set(cv2.CAP_PROP_POS_MSEC, (a - offset) * 1000)
            t, nxt = a, a
            while t <= b:
                if not cap.grab():
                    break
                if t >= nxt:
                    nxt += LOOK_EVERY
                    ok, frame = cap.retrieve()
                    if ok:
                        sc = LOOK_W / frame.shape[1]
                        out.append((t, _faces(cv2.cvtColor(cv2.resize(frame, None, fx=sc, fy=sc), cv2.COLOR_BGR2GRAY))))
                t += 1 / fps
    finally:
        cap.release()
    return out


def auto_frame(video_path, meta, moment, xs, offset=0.0):
    """Reframe settings that change through the Short (see the top of this file), or None when the video can't be
    read (the caller falls back to framing())."""
    try:
        pieces = moment.get("pieces") or [[moment["start"], moment["end"]]]
        starts = []
        for a, b in pieces:
            starts.append(a)
            for t in scene_changes(video_path, a, b, offset):
                if t - starts[-1] >= MIN_SHOT and b - t >= MIN_SHOT * 0.5:
                    starts.append(t)
        crop_w = (9 / 16) / (meta["width"] / meta["height"])
        return shot_plan(_looks(video_path, pieces, offset), starts, pieces[-1][1], xs, crop_w)
    except Exception as e:  # noqa: BLE001
        print(f"Game Mode: framing that follows the Short skipped ({e}).")
        return None
