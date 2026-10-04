"""
The thumbnail as the Short's first frame (a tenth of a second, too short for viewers to notice), so the
creator can pick it as the thumbnail in the YouTube app on any channel, Partner Program or not.

covered_video() makes "cover_<short>_<thumb>.mp4" next to the Short: a 0.1 s clip of the thumbnail, encoded
exactly like the Short (render.py), joined to it without re-encoding (a second or two). If the join isn't
clean (e.g. X264_PRESET changed since the Short was made), it's joined again with re-encoding instead.
The Short itself stays clean, so Review plays it without the flash and a new thumbnail just makes a new
cover. Used when uploading to YouTube and for the Save button.
"""
import json
import os
from pathlib import Path

from pipeline.ffmpeg import ffmpeg_exe, run


COVER_SECS = 0.1  # 3 frames at 30 fps


def audio_format(path):
    """(sample rate, channels) of the Short's sound, or None if it has none."""
    out = json.loads(run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                          "stream=sample_rate,channels", "-of", "json", str(path)]))
    st = (out.get("streams") or [None])[0]
    return (int(st["sample_rate"]), int(st["channels"])) if st else None


def plays_cleanly(path):
    """True if the whole file decodes without a single error (a bad join shows up here)."""
    try:
        return not run([ffmpeg_exe(), "-v", "error", "-i", str(path), "-f", "null", "-"]).strip() and True
    except RuntimeError:
        return False


def covered_video(job_dir, video, thumb):
    """Path of the Short `video` with the thumbnail `thumb` as its first frame (made once, then reused)."""
    job_dir = Path(job_dir)
    src, img = job_dir / video, job_dir / thumb
    out = job_dir / f"cover_{Path(video).stem}_{Path(thumb).stem}.mp4"
    if out.exists() and out.stat().st_mtime >= max(src.stat().st_mtime, img.stat().st_mtime):
        return out
    for old in job_dir.glob(f"cover_{Path(video).stem}_*.mp4"):  # an older thumbnail's cover
        old.unlink(missing_ok=True)

    audio = audio_format(src)
    clip, listing, tmp = job_dir / f"cover_clip_{out.stem}.mp4", job_dir / f"cover_list_{out.stem}.txt", \
        job_dir / f"cover_tmp_{out.stem}.mp4"
    try:
        # the cover clip, encoded with the Short's own settings so the two join without re-encoding
        cmd = [ffmpeg_exe(), "-y", "-loop", "1", "-framerate", "30", "-i", str(img)]
        if audio:
            cmd += ["-f", "lavfi", "-i", f"anullsrc=r={audio[0]}:cl={'mono' if audio[1] == 1 else 'stereo'}"]
        cmd += ["-t", f"{COVER_SECS}", "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,"
                "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p",
                "-c:v", "libx264", "-preset", os.getenv("X264_PRESET", "veryfast"), "-crf", "18",
                "-pix_fmt", "yuv420p", "-r", "30", "-video_track_timescale", "15360"]
        cmd += (["-c:a", "aac", "-b:a", "192k"] if audio else []) + [str(clip)]
        run(cmd)
        listing.write_text(f"file '{clip.name}'\nfile '{src.name}'\n", encoding="utf-8")
        run([ffmpeg_exe(), "-y", "-f", "concat", "-safe", "0", "-i", listing.name, "-c", "copy",
             "-movflags", "+faststart", tmp.name], cwd=job_dir)
        if not plays_cleanly(tmp):
            print("Cover frame: the quick join wasn't clean; joining again with re-encoding.")
            maps = "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[v][a]" if audio else "[0:v][1:v]concat=n=2:v=1:a=0[v]"
            run([ffmpeg_exe(), "-y", "-i", str(clip), "-i", str(src), "-filter_complex", maps, "-map", "[v]"]
                + (["-map", "[a]", "-c:a", "aac", "-b:a", "192k"] if audio else [])
                + ["-c:v", "libx264", "-preset", os.getenv("X264_PRESET", "veryfast"), "-crf", "18",
                   "-pix_fmt", "yuv420p", "-r", "30", "-movflags", "+faststart", str(tmp)])
        tmp.replace(out)
        return out
    finally:
        for f in (clip, listing, tmp):
            f.unlink(missing_ok=True)
