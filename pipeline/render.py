"""
Editing one Short: cut the moment, reframe to 9:16, burn in captions (FFmpeg).
"""
import os
from pathlib import Path

from pipeline.captions import build_ass
from pipeline.ffmpeg import ffmpeg_exe, run
from pipeline.reframe import crop_filter, face_center_x


def render_short(video_path, meta, moment, words, idx, style, job_dir, cx="find"):
    """Cut, reframe and caption one Short. Pass `cx` (from an earlier render of the same moment) to
    skip finding the face again, e.g. when only the hook changed."""
    job_dir = Path(job_dir)
    s, e = moment["start"], moment["end"]
    if cx == "find":
        cx = face_center_x(video_path, s, e, meta["width"])
    ass_name = f"captions_{idx}.ass"
    hook = moment.get("hook", "") if moment.get("hook_mode", "text") != "none" else ""
    build_ass(words, s, e, hook, style, job_dir / ass_name)
    out_name = f"short_{idx}.mp4"
    vf = f"{crop_filter(meta, cx)},subtitles={ass_name}:fontsdir=fonts"
    run([
        ffmpeg_exe(), "-y", "-ss", f"{s:.2f}", "-i", str(Path(video_path).resolve()), "-t", f"{e - s:.2f}",
        "-vf", vf,
        "-c:v", "libx264", "-preset", os.getenv("X264_PRESET", "medium"), "-crf", "18",
        "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out_name,
    ], cwd=job_dir)
    return out_name, cx
