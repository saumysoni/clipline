"""
Editing one Short: cut the moment, reframe to 9:16, burn in captions (FFmpeg).

A Short is one piece of the vlog (start..end) or, after AI Edit, several (moment["pieces"], pipeline/pieces.py): the
pieces are cut out and joined in one FFmpeg run, each with a 20 ms fade of its sound so the joins don't click, and the
captions follow the joined clock (pieces.timeline), in the Short's own caption settings (moment["captions"],
pipeline/captions.py; none = the job's style), framed by its reframe settings (moment["reframe"],
pipeline/smart_reframe.py; none = the crop around the face), with its text on screen (moment["overlays"],
pipeline/overlays.py).

The same FFmpeg run also writes look_<n>.mp4: the part of the vlog it read, small (LOOK_WIDTH wide), for Reframe's smart
buttons (web/reframe_look.py). A second output of a run that's decoding the vlog anyway costs ~5 % more; the Short is
the same to the bit. If that run fails, the Short is made the plain way, without the copy.
"""
import json
import os
from pathlib import Path

from pipeline.captions import build_ass
from pipeline.ffmpeg import ffmpeg_exe, run
from pipeline.pieces import kept, timeline
from pipeline.reframe import face_center_x
from pipeline.smart_reframe import drop_commands, reframe_filter

FADE = 0.02  # seconds of sound fade at each join
LOOK_WIDTH = 640  # Reframe's small copy (web/reframe_look.py)


def look_output(name, seconds):
    """FFmpeg output arguments for Reframe's small copy: the input's picture, LOOK_WIDTH wide, no sound."""
    return ["-map", "0:v:0", "-t", f"{seconds:.2f}", "-an", "-sn", "-dn", "-vf", f"scale={LOOK_WIDTH}:-2",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26", "-g", "15", "-pix_fmt", "yuv420p", name]


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


def short_words(moment, words):
    """The Short's words on its own clock, each with "i" = its position in transcript.json (what caption edits key on)."""
    return timeline(moment, [{**w, "i": k} for k, w in enumerate(words)])


def render_short(video_path, meta, moment, words, idx, style, job_dir, cx="find", offset=0.0):
    """Cut, reframe and caption one Short. Pass `cx` (from an earlier render of the same moment) to
    skip finding the face again, e.g. when only the hook changed. `offset`: the vlog second video_path starts at (a
    Short's clean clip, pipeline/clean_clip.py; the vlog itself: 0)."""
    job_dir = Path(job_dir)
    pieces = kept(moment)
    s, e = pieces[0][0], pieces[-1][1]
    if cx == "find":
        cx = face_center_x(video_path, s - offset, e - offset, meta["width"])
    ass_name = f"captions_{idx}.ass"
    hook = moment.get("hook", "") if moment.get("hook_mode", "text") != "none" else ""
    total = sum(b - a for a, b in pieces)
    build_ass(short_words(moment, words), 0.0, total, hook, style, job_dir / ass_name, moment.get("captions"),
              overlays=moment.get("overlays"), pieces=pieces)
    out_name = f"short_{idx}.mp4"
    frame, cmds = reframe_filter(meta, cx, moment.get("reframe"), pieces, job_dir)
    after = f"{frame},subtitles={ass_name}:fontsdir=fonts"
    enc = ["-c:v", "libx264", "-preset", os.getenv("X264_PRESET", "veryfast"), "-crf", "18",
           "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out_name]
    src = ["-ss", f"{s - offset:.2f}", "-i", str(Path(video_path).resolve()), "-t", f"{e - s:.2f}"]
    if len(pieces) == 1:
        cmd = [ffmpeg_exe(), "-y", *src, "-vf", after, *enc]
    else:
        # -ss before -i: the input's clock starts at s, so trim times are measured from there (to 2 decimals, as -ss)
        cmd = [ffmpeg_exe(), "-y", *src, "-filter_complex", join_filter(pieces, round(s, 2), after),
               "-map", "[vo]", "-map", "[ao]", *enc]
    look, info = f"look_{idx}.mp4", job_dir / f"look_{idx}.json"
    info.unlink(missing_ok=True)
    try:
        if not Path(video_path).name.startswith("source."):  # a clean clip (the vlog's video is gone): small already
            run(cmd, cwd=job_dir)
            return out_name, cx
        try:
            run(cmd + look_output(look, e - s), cwd=job_dir)
            start = round(s - offset, 2) + offset
            info.write_text(json.dumps({"from": round(start, 3), "to": round(start + (e - s), 3)}), encoding="utf-8")
        except RuntimeError as err:  # (not Stop or Pause: those carry on up)
            (job_dir / look).unlink(missing_ok=True)
            print(f"The Short is made without Reframe's small copy ({str(err)[:200]}).")
            run(cmd, cwd=job_dir)
    finally:
        drop_commands(job_dir, cmds)
    return out_name, cx
