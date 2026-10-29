"""
One frame of a Short with captions in given settings (the editor's Captions tool, web/captions.py), so a creator sees a
change before saving. It's drawn the way the Short is made: the vlog's frame at that moment, reframed to 9:16 the same way
(pipeline/smart_reframe.py), and the same .ass file (pipeline/captions.py) burned in by libass. So it needs the vlog's video.
caption_clip() is the same as a few seconds of silent video, for what a frame can't show: lines coming in, the spoken word.
"""
import uuid
from pathlib import Path

from pipeline.captions import build_ass
from pipeline.ffmpeg import ffmpeg_exe, run
from pipeline.pieces import kept, to_short
from pipeline.smart_reframe import drop_commands, reframe_filter
from pipeline.render import short_words

WIDTH = 540  # pixels: half size, plenty for a panel
CLIP = 2.5   # seconds of a motion preview


def short_time(moment, at):
    """A vlog time as a time in the Short (a cut time: the start of the next kept piece, else the Short's end)."""
    pieces = kept(moment)
    t = to_short(pieces, at)
    if t is not None:
        return t, at
    done = 0.0
    for a, b in pieces:
        if at < a:
            return done, a
        done += b - a
    return max(0.0, done - 0.05), pieces[-1][1] - 0.05


def caption_frame(video_path, meta, moment, words, at, style, job_dir, caps=None, offset=0.0):
    """JPEG bytes: the Short at vlog time `at` (seconds) with its hook and captions in `caps`. `offset`: the vlog second
    video_path starts at (a clean clip; the vlog: 0)."""
    job_dir = Path(job_dir)
    t, src_at = short_time(moment, float(at))
    total = sum(b - a for a, b in kept(moment))
    hook = moment.get("hook", "") if moment.get("hook_mode", "text") != "none" else ""
    name = f"capprev_{uuid.uuid4().hex[:10]}"
    ass, jpg = job_dir / f"{name}.ass", job_dir / f"{name}.jpg"
    cmds = None
    try:
        build_ass(short_words(moment, words), 0.0, total, hook, style, ass, caps)
        frame, cmds = reframe_filter(meta, moment.get("cx"), moment.get("reframe"), kept(moment), job_dir)
        # -ss before -i: one frame from there; its clock is moved to the Short's time (before the framing, which moves
        # on that clock) so the captions due then show
        vf = f"setpts=PTS-STARTPTS+{t:.3f}/TB,{frame},subtitles={ass.name}:fontsdir=fonts,scale={WIDTH}:-2"
        run([ffmpeg_exe(), "-y", "-ss", f"{max(0.0, src_at - offset):.3f}", "-i", str(Path(video_path).resolve()),
             "-frames:v", "1", "-vf", vf, "-q:v", "4", jpg.name], cwd=job_dir)
        return jpg.read_bytes()
    finally:
        drop_commands(job_dir, cmds)
        for f in (ass, jpg):
            f.unlink(missing_ok=True)


def caption_clip(video_path, meta, moment, words, at, style, job_dir, caps=None, seconds=CLIP, offset=0.0):
    """MP4 bytes: `seconds` of the Short from vlog time `at` (to the end of its piece at most), captions burned in, no
    sound (it loops in the panel)."""
    job_dir = Path(job_dir)
    t, src_at = short_time(moment, float(at))
    piece_end = next((b for a, b in kept(moment) if a <= src_at <= b), src_at + seconds)
    dur = max(0.5, min(seconds, piece_end - src_at))
    total = sum(b - a for a, b in kept(moment))
    hook = moment.get("hook", "") if moment.get("hook_mode", "text") != "none" else ""
    name = f"capprev_{uuid.uuid4().hex[:10]}"
    ass, mp4 = job_dir / f"{name}.ass", job_dir / f"{name}.mp4"
    cmds = None
    try:
        build_ass(short_words(moment, words), 0.0, total, hook, style, ass, caps)
        frame, cmds = reframe_filter(meta, moment.get("cx"), moment.get("reframe"), kept(moment), job_dir)
        vf = (f"setpts=PTS-STARTPTS+{t:.3f}/TB,{frame},"
              f"subtitles={ass.name}:fontsdir=fonts,setpts=PTS-STARTPTS,scale={WIDTH}:-2,fps=30")
        run([ffmpeg_exe(), "-y", "-ss", f"{max(0.0, src_at - offset):.3f}", "-i", str(Path(video_path).resolve()), "-t", f"{dur:.2f}",
             "-vf", vf, "-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-pix_fmt", "yuv420p",
             "-movflags", "+faststart", mp4.name], cwd=job_dir)
        return mp4.read_bytes()
    finally:
        drop_commands(job_dir, cmds)
        for f in (ass, mp4):
            f.unlink(missing_ok=True)
