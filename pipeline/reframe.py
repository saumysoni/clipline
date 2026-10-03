"""
Vertical framing: finds where the creator's face is and crops the wide video to 9:16 around it.
"""
import statistics

from pipeline.constants import OUT_H, OUT_W


def face_center_x(video_path, start, end, width):
    """Median horizontal position of the main face during the clip (None if no face).

    If face finding isn't available or fails for any reason, return None so the
    Short is simply cropped from the centre instead of the whole job failing.
    """
    try:
        return _face_center_x(video_path, start, end)
    except Exception as e:  # noqa: BLE001
        print(f"Face finding skipped ({e}); cropping from the centre.")
        return None


def _face_center_x(video_path, start, end):
    try:
        import cv2
    except ImportError:
        return None
    if not hasattr(cv2, "CascadeClassifier"):  # OpenCV 5 moved it out of the main package
        return None
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    cap = cv2.VideoCapture(str(video_path))
    xs, t = [], start
    while t < end:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        t += 1.0
        if not ok:
            continue
        scale = 640 / frame.shape[1]
        small = cv2.resize(frame, None, fx=scale, fy=scale)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(40, 40))
        if len(faces):
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            xs.append((x + w / 2) / scale)
    cap.release()
    return statistics.median(xs) if len(xs) >= 2 else None


def crop_filter(meta, center_x):
    w, h = meta["width"], meta["height"]
    if w / h <= 9 / 16 + 0.01:  # already vertical
        return (f"scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease:flags=lanczos,"
                f"pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2:black")
    cw = int(h * 9 / 16) // 2 * 2
    cx = center_x if center_x is not None else w / 2
    x = int(min(max(cx - cw / 2, 0), w - cw)) // 2 * 2
    return f"crop={cw}:{h}:{x}:0,scale={OUT_W}:{OUT_H}:flags=lanczos"
