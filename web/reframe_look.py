"""
Reframe's small copy of a Short's part of the vlog (look_<n>.mp4 next to short_<n>.mp4, 640 wide, H.264; look_<n>.json:
the vlog seconds it has), so Follow the speaker, Auto layout and Tap to track read a small video instead of the vlog
itself (often 4K / HEVC: decoding every frame of it on a small server took as long as the part plays, or longer). They
only look for faces, new shots and what was clicked, on pictures 320-640 wide, so the copy changes nothing in what they
find (tests/system/system_speed.py); the Short itself is still made from the vlog.

The render writes it (pipeline/render.py, a second output of the run that reads that part anyway), so it's there
before Reframe opens. A Short made before that gets one when Reframe opens (start(), in the background); until it's
ready, and for pieces outside it (stretched further under Trim) or a vlog whose video is gone (its clean clip is small
already), the buttons read the source as before. It goes with the vlog's video (web/vlogs.py remove_video: every
look_*) and with the Short (web/retention.py _short_files); the privacy policy says so.
"""
import json
import re
import subprocess
import threading
import traceback

from pipeline.ffmpeg import ffmpeg_exe
from pipeline.render import LOOK_WIDTH
from settings import JOBS_DIR

MAKING = set()  # (job id, file number) being made by start()
_LOCK = threading.Lock()


def number(me):
    """The file number of the Short's video (short_<n>.mp4), or None."""
    found = re.findall(r"_(\d+)\.", (me or {}).get("video") or "")
    return found[0] if found else None


def paths(job_id, num):
    d = JOBS_DIR / job_id
    return d / f"look_{num}.mp4", d / f"look_{num}.json"


def covered(job_id, num):
    """(from, to) vlog seconds the copy has, or None."""
    video, info = paths(job_id, num)
    try:
        if video.is_file():
            j = json.loads(info.read_text(encoding="utf-8"))
            return float(j["from"]), float(j["to"])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def _has(have, pieces):
    return have and have[0] <= pieces[0][0] + 0.02 and have[1] >= pieces[-1][1] - 0.02


def start(job_id, me, src, pieces):
    """A Short without a copy (made before they were): make one in the background (at the background priority)."""
    num = number(me)
    if not num or not src or src.get("clip") or not pieces or _has(covered(job_id, num), pieces):
        return
    with _LOCK:
        if (job_id, num) in MAKING:
            return
        MAKING.add((job_id, num))
    threading.Thread(target=_make, args=(job_id, num, src["path"], pieces[0][0], pieces[-1][1]), daemon=True).start()


def _make(job_id, num, path, a, b):
    from web.priority import lower
    lower()
    video, info = paths(job_id, num)
    part = video.with_name(video.stem + ".part.mp4")
    try:
        subprocess.run([ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}",
                        "-i", str(path.resolve()), "-an", "-sn", "-dn", "-vf", f"scale={LOOK_WIDTH}:-2",
                        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26", "-g", "15", "-pix_fmt", "yuv420p",
                        "-f", "mp4", str(part)], check=True, stdin=subprocess.DEVNULL, capture_output=True, timeout=1800)
        if not path.exists():  # the vlog's video was deleted meanwhile: no copy of it either
            part.unlink(missing_ok=True)
            return
        part.replace(video)
        info.write_text(json.dumps({"from": round(a, 3), "to": round(b, 3)}), encoding="utf-8")
    except Exception:  # noqa: BLE001  (the buttons read the vlog itself, as before)
        traceback.print_exc()
        part.unlink(missing_ok=True)
    finally:
        with _LOCK:
            MAKING.discard((job_id, num))


def source(job_id, me, src, pieces):
    """src (web/clean_clips.py source()) or, when the copy has these pieces, the copy: {"path", "offset", ...}."""
    num = number(me)
    if not num or not src or src.get("clip") or not pieces or not src["path"].exists():
        return src
    have = covered(job_id, num)
    if not _has(have, pieces):
        return src
    return {**src, "path": paths(job_id, num)[0], "offset": have[0]}
