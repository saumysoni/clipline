"""
Editing one Short: cut the moment, reframe to 9:16, burn in captions (FFmpeg).

A Short is one piece of the vlog (start..end) or, after AI Edit, several (moment["pieces"], pipeline/pieces.py): the
pieces are cut out and joined in one FFmpeg run, each with a 20 ms fade of its sound so the joins don't click, and the
captions follow the joined clock (pieces.timeline).
"""
import os
from pathlib import Path

from pipeline.captions import build_ass
from pipeline.ffmpeg import ffmpeg_exe, run
from pipeline.pieces import kept, timeline
from pipeline.reframe import crop_filter, face_center_x

FADE = 0.02  # seconds of sound fade at each join


def join_filter(pieces, start, after):
    """filter_complex that cuts `pieces` (vlog seconds) out of an input that begins at `start`, joins them and applies
    `after` (crop, captions) to the picture. Outputs [vo] and [ao]."""
    parts, ins = [], ""
    for k, (a, b) in enumerate(pieces):
        ra, rb, d = a - start, b - start, b - a
        fade = min(FADE, d / 4)
        parts.append(f"[0:v]trim=start={ra:.3f}:end={rb:.3f},setpts=PTS-STARTPTS[v{k}]")
        parts.append(f"[0:a]atrim=start={ra:.3f}:end={rb:.3f},asetpts=PTS-STARTPTS,"
                     f"afade=t=in:d={fade:.3f},afade=t=out:st={d - fade:.3f}:d={fade:.3f}[a{k}]")
        ins += f"[v{k}][a{k}]"
    parts.append(f"{ins}concat=n={len(pieces)}:v=1:a=1[vc][ao]")
    parts.append(f"[vc]{after}[vo]")
    return ";".join(parts)


def render_short(video_path, meta, moment, words, idx, style, job_dir, cx="find"):
    """Cut, reframe and caption one Short. Pass `cx` (from an earlier render of the same moment) to
    skip finding the face again, e.g. when only the hook changed."""
    job_dir = Path(job_dir)
    pieces = kept(moment)
    s, e = pieces[0][0], pieces[-1][1]
    if cx == "find":
        cx = face_center_x(video_path, s, e, meta["width"])
    ass_name = f"captions_{idx}.ass"
    hook = moment.get("hook", "") if moment.get("hook_mode", "text") != "none" else ""
    total = sum(b - a for a, b in pieces)
    build_ass(timeline(moment, words), 0.0, total, hook, style, job_dir / ass_name)
    out_name = f"short_{idx}.mp4"
    after = f"{crop_filter(meta, cx)},subtitles={ass_name}:fontsdir=fonts"
    enc = ["-c:v", "libx264", "-preset", os.getenv("X264_PRESET", "veryfast"), "-crf", "18",
           "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out_name]
    src = ["-ss", f"{s:.2f}", "-i", str(Path(video_path).resolve()), "-t", f"{e - s:.2f}"]
    if len(pieces) == 1:
        run([ffmpeg_exe(), "-y", *src, "-vf", after, *enc], cwd=job_dir)
    else:
        # -ss before -i: the input's clock starts at s, so trim times are measured from there (to 2 decimals, as -ss)
        run([ffmpeg_exe(), "-y", *src, "-filter_complex", join_filter(pieces, round(s, 2), after),
             "-map", "[vo]", "-map", "[ao]", *enc], cwd=job_dir)
    return out_name, cx
