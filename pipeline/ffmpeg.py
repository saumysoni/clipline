"""
Running FFmpeg and reading a video's size, rotation and length.

Not every FFmpeg can burn captions (some builds have no libass), so ffmpeg_exe() picks one that can.
Always call ffmpeg_exe(); never hard-code "ffmpeg".
"""
import json
import os
import shutil
import subprocess


_FFMPEG = None


def ffmpeg_has_captions(exe):
    """True if this FFmpeg can burn in captions (it needs the 'subtitles' feature, from libass)."""
    try:
        out = subprocess.run([exe, "-hide_banner", "-filters"], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return any(line.split()[1:2] == ["subtitles"] for line in out.splitlines() if line.strip())


def ffmpeg_exe():
    """The FFmpeg to use. Some FFmpeg installs (for example newer Homebrew or Anaconda builds)
    leave out caption support; in that case use the complete copy from the imageio-ffmpeg add-on."""
    global _FFMPEG
    if _FFMPEG:
        return _FFMPEG
    candidates = [os.getenv("FFMPEG_PATH"), shutil.which("ffmpeg"),
                  "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"]
    try:
        import imageio_ffmpeg
        candidates.append(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:  # noqa: BLE001  (add-on missing or no binary for this computer)
        pass
    seen = []
    for exe in candidates:
        if exe and exe not in seen and os.path.exists(exe):
            seen.append(exe)
            if ffmpeg_has_captions(exe):
                _FFMPEG = exe
                print(f"Using FFmpeg: {exe}")
                return exe
    if not seen:
        raise RuntimeError("FFmpeg isn't installed. See README step 1.")
    raise RuntimeError("Your FFmpeg can't add captions, and the backup copy is missing. Close Pit Crew and "
                       "start it again with the start script so it can install the missing add-on.")


def run(cmd, cwd=None):
    """Run a command and raise a readable error if it fails."""
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if p.returncode != 0:
        tail = "\n".join(p.stderr.strip().splitlines()[-12:])
        raise RuntimeError(f"Command failed: {' '.join(map(str, cmd[:3]))} ...\n{tail}")
    return p.stdout


def probe(path):
    # Ask for the full stream info (works on old and new FFmpeg versions alike).
    out = run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_streams", "-show_format", "-of", "json", str(path),
    ])
    info = json.loads(out)
    if not info.get("streams"):
        raise RuntimeError("This file doesn't contain a video track. Please use a normal video file.")
    st = info["streams"][0]
    w, h = int(st["width"]), int(st["height"])
    rot = 0
    for sd in st.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = abs(int(float(sd["rotation"]))) % 360
    if not rot and str((st.get("tags") or {}).get("rotate", "")).lstrip("-").isdigit():
        rot = abs(int(st["tags"]["rotate"])) % 360  # older FFmpeg reports it here
    if rot in (90, 270):  # phone videos stored sideways
        w, h = h, w
    return {"width": w, "height": h, "duration": float(info["format"]["duration"])}
