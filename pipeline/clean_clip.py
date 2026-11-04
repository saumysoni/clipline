"""
A draft Short's clean clip: its moment and PAD seconds either side, cut from the vlog's wide picture with no captions or
hook, made just before the vlog's video is deleted (web/clean_clips.py, gotcha 35). The editor's tools that remake the
Short (Captions, Reframe, the hook, AI Edit and Trim inside that reach) then work from it instead of the vlog, which is
GBs; a clip is tens of MB. Times stay the vlog's seconds everywhere: the clip starts at `from`, so a tool reads it at
(vlog time - from) (the `offset` of render_short, caption_frame, follow_moves). Pictures over 1080 on their short side
are made 1080 (`scale` = clip width / vlog width: positions in pixels, like a Short's face `cx`, are scaled by it).
"""
import os
from pathlib import Path

from pipeline.ffmpeg import ffmpeg_exe, run

PAD = 30.0  # seconds of the vlog kept either side of the Short


def clip_reach(pieces, duration, pad=PAD):
    """(from, to) in vlog seconds: the Short's parts and `pad` either side, inside the vlog."""
    a, b = pieces[0][0] - pad, pieces[-1][1] + pad
    return round(max(0.0, a), 3), round(min(float(duration or b), b), 3)


def make_clean_clip(video_path, meta, a, b, out_path):
    """Cut a..b (vlog seconds) of the vlog to out_path (H.264 + AAC). Returns {"from", "to", "scale"}."""
    w, h = meta["width"], meta["height"]
    short = min(w, h)
    scale = min(1.0, 1080 / short) if short else 1.0
    vf = [] if scale >= 1 else [f"scale={int(round(w * scale / 2)) * 2}:{int(round(h * scale / 2)) * 2}:flags=lanczos"]
    out_path = Path(out_path)
    part = out_path.with_name(out_path.stem + ".part.mp4")
    run([ffmpeg_exe(), "-y", "-ss", f"{a:.3f}", "-i", str(Path(video_path).resolve()), "-t", f"{b - a:.3f}",
         *(["-vf", vf[0]] if vf else []), "-c:v", "libx264", "-preset", os.getenv("X264_PRESET", "veryfast"), "-crf", "20",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(part)])
    part.replace(out_path)
    return {"from": round(a, 3), "to": round(b, 3), "scale": round(scale, 6)}
