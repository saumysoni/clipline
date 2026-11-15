"""
One frame of a Short with captions in given settings (the editor's Captions tool, web/captions.py), so a creator sees a
change before saving. It's drawn the way the Short is made: the vlog's frame at that moment, reframed to 9:16 the same way
(pipeline/smart_reframe.py), and the same .ass file (pipeline/captions.py) burned in by libass. So it needs the vlog's video.
caption_clip() is the same as a few seconds of silent video, for what a frame can't show: lines coming in, the spoken word.
"""
import os
import threading
import uuid
from collections import OrderedDict
from pathlib import Path

from pipeline.captions import build_ass
from pipeline.ffmpeg import ffmpeg_exe, run
from pipeline.pieces import kept, to_short
from pipeline.smart_reframe import drop_commands, reframe_filter
from pipeline.render import short_words

WIDTH = 540  # pixels: half size, plenty for a panel
CLIP = 2.5   # seconds of a motion preview

# The framed picture of the last few previews (before captions), so changing the captions at the same moment only draws the
# captions again: finding and decoding the vlog's frame was most of the time (0.3-0.8 s on a small server, 4K / HEVC the
# most). Keyed on the file (and its size and time), the moment and the framing; a moving frame (a command file) isn't kept.
_BASES = OrderedDict()
_BASES_MAX = 12
_BASES_LOCK = threading.Lock()


def _base_key(video_path, src_at, t, frame):
    try:
        st = os.stat(video_path)
    except OSError:
        return None
    return (str(Path(video_path).resolve()), st.st_size, st.st_mtime_ns, round(src_at, 3), round(t, 3), frame)


def _remember_base(key, data):
    with _BASES_LOCK:
        _BASES[key] = data
        _BASES.move_to_end(key)
        while len(_BASES) > _BASES_MAX:
            _BASES.popitem(last=False)


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
    ass, jpg, base = job_dir / f"{name}.ass", job_dir / f"{name}.jpg", job_dir / f"{name}_base.jpg"
    cmds = None
    try:
        build_ass(short_words(moment, words), 0.0, total, hook, style, ass, caps, overlays=moment.get("overlays"),
                  pieces=kept(moment))
        frame, cmds = reframe_filter(meta, moment.get("cx"), moment.get("reframe"), kept(moment), job_dir)
        key = None if cmds else _base_key(video_path, src_at - offset, t, frame)
        with _BASES_LOCK:
            kept_base = _BASES.get(key) if key else None
        captions = f"subtitles={ass.name}:fontsdir=fonts,scale={WIDTH}:-2"
        if kept_base:  # the same picture: only the captions are drawn on it (the clock set to the Short's time again)
            base.write_bytes(kept_base)
            run([ffmpeg_exe(), "-y", "-i", base.name, "-frames:v", "1", "-vf", f"setpts=PTS-STARTPTS+{t:.3f}/TB,{captions}",
                 "-q:v", "4", jpg.name], cwd=job_dir)
            return jpg.read_bytes()
        # -ss before -i: one frame from there; its clock is moved to the Short's time (before the framing, which moves
        # on that clock) so the captions due then show
        vf = f"setpts=PTS-STARTPTS+{t:.3f}/TB,{frame}"
        if not key:
            run([ffmpeg_exe(), "-y", "-ss", f"{max(0.0, src_at - offset):.3f}", "-i", str(Path(video_path).resolve()),
                 "-frames:v", "1", "-vf", f"{vf},{captions}", "-q:v", "4", jpg.name], cwd=job_dir)
            return jpg.read_bytes()
        # the framed picture is kept too (the same FFmpeg run: one decode)
        run([ffmpeg_exe(), "-y", "-ss", f"{max(0.0, src_at - offset):.3f}", "-i", str(Path(video_path).resolve()),
             "-filter_complex", f"[0:v]{vf},split[pcbase][pccap];[pccap]{captions}[pcout]",
             "-map", "[pcbase]", "-frames:v", "1", "-q:v", "2", base.name,
             "-map", "[pcout]", "-frames:v", "1", "-q:v", "4", jpg.name], cwd=job_dir)
        _remember_base(key, base.read_bytes())
        return jpg.read_bytes()
    finally:
        drop_commands(job_dir, cmds)
        for f in (ass, jpg, base):
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
        build_ass(short_words(moment, words), 0.0, total, hook, style, ass, caps, overlays=moment.get("overlays"),
                  pieces=kept(moment))
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
