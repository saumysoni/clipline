"""
Thumbnails, step 1: frames spread across the Short, and finding faces in them.
"""
from pathlib import Path

import numpy as np
from PIL import Image

from pipeline.ffmpeg import ffmpeg_exe, run


N_FRAMES = 10


def sample_frames(video_path, start, end, work, n=N_FRAMES):
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    span = max(0.5, end - start - 1.0)
    frames = []
    for k in range(n):
        t = start + 0.5 + span * (k + 0.5) / n
        out = work / f"frame_{k}.jpg"
        run([ffmpeg_exe(), "-y", "-ss", f"{t:.2f}", "-i", str(Path(video_path).resolve()),
               "-frames:v", "1", "-vf", "scale='min(1280,iw)':-2", "-q:v", "2", str(out)])
        if out.exists():
            frames.append(Image.open(out).convert("RGB"))
    if not frames:
        raise RuntimeError("couldn't read frames")
    return frames


def find_faces(img):
    """Largest face (x, y, w, h) in pixels plus a quality score, or (None, 0)."""
    try:
        import cv2
        if not hasattr(cv2, "CascadeClassifier"):
            return None, 0.0
        gray = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(max(40, img.width // 20),) * 2)
        if not len(faces):
            return None, 0.0
        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
        sharp = cv2.Laplacian(gray[y:y + h, x:x + w], cv2.CV_64F).var()
        return (int(x), int(y), int(w), int(h)), (w * h) / (img.width * img.height) * (sharp ** 0.5)
    except Exception:  # noqa: BLE001
        return None, 0.0
