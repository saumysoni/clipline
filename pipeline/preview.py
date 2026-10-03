"""
A small, browser-friendly copy of the vlog for choosing a scene on the video.
"""
from pathlib import Path

from pipeline.ffmpeg import ffmpeg_exe, run


def make_preview(video_path, out_path):
    """A small copy of the whole vlog for choosing scenes in the browser.

    The original may be 4K, HEVC or HDR, which many browsers can't play (or load slowly);
    this small H.264 copy (480p, 24 fps, ~8 MB a minute) plays everywhere, with a keyframe every second
    so scrubbing is quick.
    """
    out_path = Path(out_path)
    tmp = out_path.with_name(out_path.stem + ".part.mp4")
    # -hwaccel auto decodes with the machine's video hardware when it has some (reading 4K/HEVC/HDR is the
    # slow part) and falls back to the processor by itself, so this works the same on any server.
    run([ffmpeg_exe(), "-y", "-hwaccel", "auto", "-i", str(Path(video_path).resolve()),
         "-vf", "fps=24,scale='if(gt(iw,ih),-2,480)':'if(gt(iw,ih),480,-2)'",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "33", "-g", "24", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "96k", "-ac", "2", "-movflags", "+faststart", str(tmp)])
    tmp.replace(out_path)
    return out_path.name
