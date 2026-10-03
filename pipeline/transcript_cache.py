"""
Saved transcripts: uploading the same vlog again skips transcription.

Each transcript is also kept in jobs/_transcripts, named after a fingerprint of the video file.
"""
import hashlib
import shutil
from pathlib import Path

from settings import JOBS_DIR


# Transcribing a long vlog takes a while, so each transcript is also saved under
# jobs/_transcripts, named after a fingerprint of the video. Uploading the same video
# again (e.g. after a Gemini hiccup) reuses it instead of transcribing again.
TRANSCRIPTS_DIR = JOBS_DIR / "_transcripts"


def video_fingerprint(path):
    path = Path(path)
    size = path.stat().st_size
    h = hashlib.sha1(str(size).encode())
    with open(path, "rb") as f:
        h.update(f.read(4 << 20))
        if size > 8 << 20:
            f.seek(-(4 << 20), 2)
            h.update(f.read())
    return h.hexdigest()[:20]


def find_saved_transcript(src):
    try:
        fp = video_fingerprint(src)
        cached = TRANSCRIPTS_DIR / f"{fp}.json"
        if cached.exists():
            return cached
        # Older jobs (made before this feature) may already hold a transcript of this video.
        for other in JOBS_DIR.glob("*/transcript.json"):
            for vid in other.parent.glob("source.*"):
                if vid.resolve() != Path(src).resolve() and vid.stat().st_size == Path(src).stat().st_size \
                        and video_fingerprint(vid) == fp:
                    return other
    except OSError:
        pass
    return None


def remember_transcript(src, job_tr):
    try:
        TRANSCRIPTS_DIR.mkdir(exist_ok=True)
        cached = TRANSCRIPTS_DIR / f"{video_fingerprint(src)}.json"
        if Path(job_tr).exists() and not cached.exists():
            shutil.copy(job_tr, cached)
    except OSError:
        pass
