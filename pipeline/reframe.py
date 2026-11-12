"""
Vertical framing: finds where the creator's face is and crops the wide video to 9:16 around it.
"""
import statistics
from pathlib import Path

from pipeline.constants import OUT_H, OUT_W


def face_center_x(video_path, start, end, width):
    """Median horizontal position of the main face during the clip (None if no face).

    If face finding isn't available or fails for any reason, return None so the
    Short is simply cropped from the centre instead of the whole job failing.
    """
    try:
        return _face_center_x(video_path, start, end, width)
    except Exception as e:  # noqa: BLE001
        print(f"Face finding skipped ({e}); cropping from the centre.")
        return None


LOOK_WIDTH = 640  # faces are looked for on a copy this wide


def _face_center_x(video_path, start, end, width=None):
    try:
        import cv2
    except ImportError:
        return None
    if not hasattr(cv2, "CascadeClassifier"):  # OpenCV 5 moved it out of the main package
        return None
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    xs = []
    for gray, wide in _looks(video_path, start, end, width):
        faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(40, 40))
        if len(faces):
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            xs.append((x + w / 2) * wide / gray.shape[1])
    return statistics.median(xs) if len(xs) >= 2 else None


def _looks(video_path, start, end, width):
    """About one small grey picture a second between start and end, as (picture, the video's width).

    The video's keyframes when there are enough of them (a phone puts one every second or two): only those are decoded,
    several times quicker than reading the clip, which counts most on a small server and with 4K / HEVC. Otherwise
    (few keyframes, or that didn't work) the clip is read through once, a picture taken every second."""
    if width:
        try:
            pics = key_frames(video_path, start, end, LOOK_WIDTH)
            if len(pics) >= max(2, (end - start) / 2.5):
                return [(p, width) for p in pics]
        except Exception as e:  # noqa: BLE001  (read it the long way)
            print(f"Keyframes couldn't be read ({str(e)[:200]}); reading the clip.")
    return _every_second(video_path, start, end)


def key_frames(video_path, start, end, look_width):
    """The keyframes between start and end, look_width wide and grey (numpy arrays), decoding nothing else."""
    import subprocess

    import numpy as np
    from pipeline.ffmpeg import ffmpeg_exe
    span = max(0.1, end - start)
    p = subprocess.run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-skip_frame", "nokey",
                        "-ss", f"{max(0.0, start):.3f}", "-t", f"{span:.3f}", "-i", str(Path(video_path).resolve()),
                        "-an", "-sn", "-vf", f"scale={look_width}:-2,format=gray", "-vsync", "passthrough",
                        "-f", "image2pipe", "-c:v", "pgm", "-"], stdin=subprocess.DEVNULL, capture_output=True, timeout=600)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode(errors="replace").strip()[-300:])
    data, pics, at = p.stdout, [], 0
    while data.startswith(b"P5", at):  # each picture: "P5\n<w> <h>\n255\n" then w*h bytes
        head = data[at:at + 64].split(b"\n", 3)
        w, h = map(int, head[1].split())
        body = at + sum(len(x) + 1 for x in head[:3])
        pics.append(np.frombuffer(data, np.uint8, w * h, body).reshape(h, w))
        at = body + w * h
    if len(pics) > span * 4 + 2:  # more than keyframes can be (this FFmpeg repeated pictures): not to be trusted
        return []
    return pics


def _every_second(video_path, start, end):
    import cv2
    cap = cv2.VideoCapture(str(video_path))
    out = []
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000)  # one seek, then read on (a seek per picture decoded far more)
        t, nxt = start, start
        while t < end:
            if not cap.grab():
                break
            if t >= nxt - 0.5 / fps:
                ok, frame = cap.retrieve()
                nxt += 1.0
                if ok:
                    scale = LOOK_WIDTH / frame.shape[1]
                    out.append((cv2.cvtColor(cv2.resize(frame, None, fx=scale, fy=scale), cv2.COLOR_BGR2GRAY), frame.shape[1]))
            t += 1 / fps
    finally:
        cap.release()
    return out


def crop_filter(meta, center_x):
    w, h = meta["width"], meta["height"]
    if w / h <= 9 / 16 + 0.01:  # already vertical
        return (f"scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease:flags=lanczos,"
                f"pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2:black")
    cw = int(h * 9 / 16) // 2 * 2
    cx = center_x if center_x is not None else w / 2
    x = int(min(max(cx - cw / 2, 0), w - cw)) // 2 * 2
    return f"crop={cw}:{h}:{x}:0,scale={OUT_W}:{OUT_H}:flags=lanczos"
