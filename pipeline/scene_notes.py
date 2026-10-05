"""
Scene notes: short descriptions of what's *seen* in the vlog, every few seconds, so "when was I climbing the
mountain?" can be answered even when nothing was said. Made once from small frames (the AI looks at them in
batches) and kept as text (scenes.json, a few KB), so they outlive the vlog's video (web/retention.py).

Settings: SCENE_NOTES=0 turns them off; SCENE_EVERY (seconds between frames, default 10); SCENE_MAX_FRAMES (cap
for long vlogs, default 240: a 40-minute vlog is then read every 10 s, a 2-hour one every 30 s).
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

from pipeline.ai import ai_json, image_part
from pipeline.ffmpeg import ffmpeg_exe
from pipeline.text import fmt_mmss

BATCH = 20  # frames per AI request

PROMPT = ("These are frames from a travel/lifestyle vlog, in order, each labelled with its time in the video. For each "
          "frame, write one short factual note (under 15 words) of what is visible: the place, what the person is "
          "doing, notable things (food, animals, vehicles, views, weather). Describe only what you can see. Don't guess "
          "names of people or places unless written in the frame. Return JSON: a list of {\"t\": <the frame's time in "
          "seconds, as given>, \"scene\": \"...\"}.")


def enabled():
    return os.getenv("SCENE_NOTES", "1") != "0"


def _frames(video_path, duration, work, every):
    """Small frames every `every` seconds, decoding only keyframes (fast even for long 4K vlogs).
    Returns [(time_seconds, path)]."""
    work.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error", "-skip_frame", "nokey",
           "-i", str(Path(video_path).resolve()), "-vf", f"fps=1/{every},scale=320:-2", "-fps_mode", "vfr",
           "-q:v", "5", str(work / "f_%05d.jpg")]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:  # older FFmpeg: -vsync instead of -fps_mode
        cmd[cmd.index("-fps_mode")] = "-vsync"
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError("Couldn't read frames from the video: " + p.stderr.strip()[-300:])
    files = sorted(work.glob("f_*.jpg"))
    return [(min(duration, (k + 0.5) * every), f) for k, f in enumerate(files)]


def make_scene_notes(video_path, duration, out_path, progress=lambda pct, msg: None):
    """Write scenes.json: [{"t": seconds, "text": "..."}] for the whole vlog. Returns the notes."""
    every = max(float(os.getenv("SCENE_EVERY", "10")), duration / max(1, int(os.getenv("SCENE_MAX_FRAMES", "240"))))
    work = Path(out_path).parent / "scenework"
    try:
        progress(5, "Looking through the video")
        frames = _frames(video_path, duration, work, every)
        notes = []
        for b in range(0, len(frames), BATCH):
            batch = frames[b:b + BATCH]
            contents = [PROMPT]
            for t, f in batch:
                contents += [f"Frame at {t:.0f} seconds ({fmt_mmss(t)}):", image_part(f.read_bytes())]
            raw = ai_json(contents, temperature=0.2)
            rows = raw.get("items", raw) if isinstance(raw, dict) else raw
            times = [t for t, _ in batch]
            for r in rows if isinstance(rows, list) else []:
                try:
                    t, text = float(r["t"]), str(r.get("scene") or r.get("text") or "").strip()[:160]
                except (KeyError, TypeError, ValueError):
                    continue
                if text:
                    notes.append({"t": round(min(times, key=lambda x: abs(x - t)), 1), "text": text})
            progress(10 + 90 * min(1, (b + BATCH) / max(1, len(frames))), "Noting what's in the video")
        notes.sort(key=lambda n: n["t"])
        Path(out_path).write_text(json.dumps(notes), encoding="utf-8")
        return notes
    finally:
        shutil.rmtree(work, ignore_errors=True)
