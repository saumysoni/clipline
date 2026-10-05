"""
A small, browser-friendly copy of the vlog for choosing a scene on the video.
"""
import subprocess
from pathlib import Path

from pipeline.ffmpeg import ffmpeg_exe, probe


def plays_everywhere(video_path, meta):
    """True if every browser can play the original as it is (8-bit H.264 in an MP4/MOV), so "Choose on the video"
    can use it straight away and no preview copy is needed. iPhone HEVC/HDR, 10-bit, MKV etc. still get the copy."""
    return (meta.get("codec") == "h264" and meta.get("pix_fmt") in ("yuv420p", "yuvj420p")
            and Path(video_path).suffix.lower() in (".mp4", ".m4v", ".mov"))


def make_preview(video_path, out_path, progress=None):
    """A small copy of the whole vlog for choosing scenes in the browser.

    The original may be 4K, HEVC or HDR, which many browsers can't play (or load slowly);
    this small H.264 copy (480p, 24 fps, ~8 MB a minute) plays everywhere, with a keyframe every second
    so scrubbing is quick. progress(pct) is called as it goes (0-100).
    """
    out_path = Path(out_path)
    tmp = out_path.with_name(out_path.stem + ".part.mp4")
    # -hwaccel auto decodes with the machine's video hardware when it has some (reading 4K/HEVC/HDR is the
    # slow part) and falls back to the processor by itself, so this works the same on any server.
    duration = probe(video_path)["duration"] or 0
    cmd = [ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error", "-nostats", "-progress", "pipe:1",
           "-hwaccel", "auto", "-i", str(Path(video_path).resolve()),
           "-vf", "fps=24,scale='if(gt(iw,ih),-2,480)':'if(gt(iw,ih),480,-2)'",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "33", "-g", "24", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "96k", "-ac", "2", "-movflags", "+faststart", str(tmp)]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for line in p.stdout:  # "-progress" writes key=value lines; out_time_us is how far it has got
        if progress and duration and line.startswith("out_time_us="):
            try:
                progress(min(99, int(line.split("=", 1)[1]) / 1e6 / duration * 100))
            except ValueError:
                pass
    err = p.stderr.read()
    if p.wait() != 0:
        tail = "\n".join(err.strip().splitlines()[-12:])
        raise RuntimeError(f"Command failed: {' '.join(map(str, cmd[:3]))} ...\n{tail}")
    tmp.replace(out_path)
    return out_path.name
