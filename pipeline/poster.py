"""
A vlog's poster: one landscape frame (640 px wide JPEG, a few tens of KB) for the Vlogs list, taken a little way
into the video so it isn't a black intro frame. Kept after the vlog's video is deleted (web/retention.py only
removes the video files).
"""
from pathlib import Path

from pipeline.ffmpeg import ffmpeg_exe, run


def make_poster(video_path, out_path, duration=0):
    """Write the poster to out_path (via a temporary file, so a half-written one is never shown)."""
    out_path = Path(out_path)
    tmp = out_path.with_name(out_path.stem + ".part.jpg")
    at = max(1.0, min(float(duration or 0) * 0.12, 120.0))
    run([ffmpeg_exe(), "-y", "-loglevel", "error", "-ss", f"{at:.2f}", "-i", str(video_path), "-frames:v", "1",
         "-vf", "scale=640:-2", "-q:v", "4", str(tmp)])
    tmp.replace(out_path)
