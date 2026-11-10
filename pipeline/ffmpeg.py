"""
Running FFmpeg and reading a video's size, rotation and length.

Not every FFmpeg can burn captions (some builds have no libass), so ffmpeg_exe() picks one that can.
Always call ffmpeg_exe(); never hard-code "ffmpeg".
"""
import contextlib
import json
import os
import shutil
import subprocess
import tempfile
import threading


_FFMPEG = None
_WATCH = threading.local()  # what run() does in this thread (watching() below)


@contextlib.contextmanager
def watching(check=None, on_time=None):
    """For FFmpeg runs in this thread. check(): called about 5 times a second; if it raises, FFmpeg is killed at once and
    the exception carries on (Pause and Stop). on_time(seconds): how much of the output is done (a progress ring).
    Pipeline code doesn't need to know: it keeps calling run()."""
    was = getattr(_WATCH, "check", None), getattr(_WATCH, "on_time", None)
    _WATCH.check, _WATCH.on_time = check or was[0], on_time or was[1]
    try:
        yield
    finally:
        _WATCH.check, _WATCH.on_time = was


def ffmpeg_has_captions(exe):
    """True if this FFmpeg can burn in captions (it needs the 'subtitles' feature, from libass)."""
    try:
        out = subprocess.run([exe, "-hide_banner", "-filters"], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30).stdout
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
        print("FFmpeg isn't installed (README step 1).")
    else:
        print("No FFmpeg with the subtitles filter (libass) found, and imageio-ffmpeg is missing: "
              "reinstall requirements.txt.")
    raise RuntimeError("Pit Crew's video editor isn't working right now. Try again later; if it keeps "
                       "happening, tell us.")


def run(cmd, cwd=None):
    """Run a command and raise a readable error if it fails.
    stdin is always empty: FFmpeg reads keys from a terminal while it encodes, and started from one in the background
    (deploy/update.sh runs the tests under `timeout`) the system stops it the moment it tries, so it hung for ever."""
    check, on_time = getattr(_WATCH, "check", None), getattr(_WATCH, "on_time", None)
    if check or on_time:
        return _run_watched(cmd, cwd, check, on_time)
    p = subprocess.run(cmd, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True, text=True)
    if p.returncode != 0:
        tail = "\n".join(p.stderr.strip().splitlines()[-12:])
        raise RuntimeError(f"Command failed: {' '.join(map(str, cmd[:3]))} ...\n{tail}")
    return p.stdout


def _run_watched(cmd, cwd, check, on_time):
    """run() with watching()'s check and on_time. stderr goes to a file so a full pipe can never hold FFmpeg up."""
    if check:
        check()
    is_ffmpeg = "ffmpeg" in os.path.basename(str(cmd[0]))
    if on_time and is_ffmpeg:
        cmd = [cmd[0], "-progress", "pipe:1", "-nostats", *cmd[1:]]
    lines = []

    def read(out):
        for line in out:
            lines.append(line)
            if on_time and is_ffmpeg and line.startswith("out_time_us="):
                with contextlib.suppress(ValueError):
                    on_time(max(0.0, int(line.split("=", 1)[1]) / 1e6))

    with tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace") as err:
        p = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=err, text=True, errors="replace")
        reader = threading.Thread(target=read, args=(p.stdout,), daemon=True)
        reader.start()
        try:
            while True:
                try:
                    p.wait(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    if check:
                        check()
        except BaseException:
            p.kill()
            p.wait()
            raise
        reader.join(timeout=5)
        if p.returncode != 0:
            err.seek(0)
            tail = "\n".join(err.read().strip().splitlines()[-12:])
            raise RuntimeError(f"Command failed: {' '.join(map(str, cmd[:3]))} ...\n{tail}")
    return "".join(lines)


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
    return {"width": w, "height": h, "duration": float(info["format"]["duration"]),
            "codec": st.get("codec_name", ""), "pix_fmt": st.get("pix_fmt", "")}
