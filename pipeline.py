"""
Clipline pipeline: one long vlog in, N finished vertical Shorts out.

Steps
  1. transcribe()      faster-whisper, word-level timestamps (runs on your computer, free)
  2. pick_moments()    Gemini (free API tier) reads the transcript and picks the best moments
  3. render_short()    FFmpeg cuts, reframes to 9:16 around the face, burns in animated captions
  4. make_thumbnail()  Pillow draws a bold vertical thumbnail from a frame of the clip
"""
import json
import os
import re
import shutil
import statistics
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FONTS_DIR = ROOT / "fonts"

MIN_LEN = 15      # seconds
MAX_LEN = 59      # keep Shorts under a minute; they perform best short
OUT_W, OUT_H = 1080, 1920


# --------------------------------------------------------------------------- helpers
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
    raise RuntimeError("Your FFmpeg can't add captions, and the backup copy is missing. Close Clipline and "
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


def fmt_mmss(sec):
    sec = int(sec)
    return f"{sec // 60}:{sec % 60:02d}"


def find_font_file():
    """A bold TTF/OTF for thumbnails. Put your own in ./fonts to control the look."""
    if FONTS_DIR.exists():
        for f in sorted(FONTS_DIR.iterdir()):
            if f.suffix.lower() in (".ttf", ".otf"):
                return str(f)
    for f in [
        "C:/Windows/Fonts/arialbd.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]:
        if os.path.exists(f):
            return f
    return None


def font_family(path):
    try:
        from PIL import ImageFont
        return ImageFont.truetype(str(path), 20).getname()[0]
    except Exception:  # noqa: BLE001
        return None


def caption_font_name(job_fonts=None):
    """Family name libass should use for burned-in captions.

    Uses CAPTION_FONT when that font is in the fonts folder; otherwise the font that is
    there, so captions never come out in a missing font (or not at all).
    """
    wanted = os.getenv("CAPTION_FONT", "Montserrat ExtraBold")
    if not job_fonts or not Path(job_fonts).exists():
        return wanted
    families = [f for f in (font_family(p) for p in sorted(Path(job_fonts).iterdir())
                            if p.suffix.lower() in (".ttf", ".otf")) if f]
    if not families or wanted.lower() in (f.lower() for f in families):
        return wanted
    return families[0]


# --------------------------------------------------------------------------- 1. transcribe
SAMPLE_RATE = 16000  # what Whisper expects


def load_audio(video_path):
    """Decode the soundtrack with FFmpeg (16 kHz mono) instead of faster-whisper's own decoder.

    faster-whisper's built-in decoder relies on the PyAV library, and newer PyAV releases
    break it ("open() got an unexpected keyword argument 'metadata_errors'").
    FFmpeg is already required for editing, so this works on every machine.
    """
    import numpy as np

    p = subprocess.run(
        [ffmpeg_exe(), "-nostdin", "-v", "error", "-i", str(video_path), "-vn",
         "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "f32le", "-"],
        capture_output=True,
    )
    if p.returncode != 0:
        tail = "\n".join(p.stderr.decode("utf-8", "replace").strip().splitlines()[-8:])
        raise RuntimeError(f"Couldn't read the audio from this video.\n{tail}")
    audio = np.frombuffer(p.stdout, dtype=np.float32)
    if audio.size < SAMPLE_RATE:
        raise RuntimeError("This video has no usable sound, so there's nothing to transcribe.")
    return audio


# Transcription runs the same way everywhere: faster-whisper uses an NVIDIA GPU when the machine
# has one (e.g. a GPU cloud server) and the processor otherwise. Nothing here is specific to one
# kind of computer; tune it per machine with the WHISPER_* settings in .env / the environment.
_MODELS = {}


def available_cpus():
    try:
        return len(os.sched_getaffinity(0))  # respects CPU limits on Linux servers
    except AttributeError:
        return os.cpu_count() or 4


def whisper_model(model_name):
    """Load the speech model once per process and reuse it for every job."""
    from faster_whisper import WhisperModel

    device = os.getenv("WHISPER_DEVICE", "auto")             # auto | cpu | cuda
    compute = os.getenv("WHISPER_COMPUTE_TYPE", "auto")      # auto | int8 | float16 | ...
    threads = int(os.getenv("WHISPER_THREADS") or 0) or available_cpus()
    key = (model_name, device, compute, threads)
    if key not in _MODELS:
        try:
            _MODELS[key] = WhisperModel(model_name, device=device, compute_type=compute, cpu_threads=threads)
        except Exception as e:  # noqa: BLE001  (e.g. a GPU without the right drivers)
            if device == "cpu":
                raise
            print(f"Couldn't use the GPU ({e}); using the processor.")
            _MODELS[key] = WhisperModel(model_name, device="cpu", compute_type="auto", cpu_threads=threads)
    return _MODELS[key]


def detect_language(model, audio, samples=8, window_s=30):
    """Vote over short clips spread across the whole video.

    Whisper's own guess only listens to the start, and noise (cars, music) there can make it pick
    the wrong language (an English vlog came out as Welsh in testing).
    """
    from collections import defaultdict

    win = window_s * SAMPLE_RATE
    if len(audio) <= win * 2:
        starts = [0]
    else:
        starts = [int((k + 0.5) / samples * len(audio)) - win // 2 for k in range(samples)]
    votes = defaultdict(float)
    for st in starts:
        piece = audio[max(0, st):max(0, st) + win]
        try:
            _, _, probs = model.detect_language(piece, vad_filter=True, language_detection_segments=1)
        except Exception:  # noqa: BLE001  (e.g. a clip with no speech at all)
            continue
        for lang, prob in probs[:5]:
            votes[lang] += prob
    return max(votes, key=votes.get) if votes else None


def sentence_segments(words, max_len=12.0, max_gap=0.8):
    """Rebuild short, sentence-sized lines from word timings (what Gemini reads to pick moments)."""
    segs, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        ends_sentence = w["w"][-1:] in ".?!" and cur[-1]["e"] - cur[0]["s"] >= 2.0
        pause = nxt is not None and nxt["s"] - w["e"] >= max_gap
        too_long = cur[-1]["e"] - cur[0]["s"] >= max_len
        if nxt is None or ends_sentence or pause or too_long:
            segs.append({"s": cur[0]["s"], "e": cur[-1]["e"], "text": " ".join(x["w"] for x in cur)})
            cur = []
    return segs


def transcribe(video_path, out_json, progress=lambda pct, msg: None):
    """Word-level transcript. Cached in out_json so re-runs are instant."""
    out_json = Path(out_json)
    if out_json.exists():
        return json.loads(out_json.read_text(encoding="utf-8"))

    model_name = os.getenv("WHISPER_MODEL", "small")
    progress(0, "Extracting the audio")
    audio = load_audio(video_path)
    total = len(audio) / SAMPLE_RATE

    progress(0, f"Loading speech model ({model_name})")
    started = time.time()
    model = whisper_model(model_name)
    language = os.getenv("WHISPER_LANGUAGE") or None
    if not language and not model_name.endswith(".en"):
        progress(0, "Working out the language")
        language = detect_language(model, audio)

    progress(0, "Listening to the vlog")
    batch = int(os.getenv("WHISPER_BATCH_SIZE", "8") or 0)
    words, engine = None, None
    if batch > 0:
        try:
            from faster_whisper import BatchedInferencePipeline
            segments, info = BatchedInferencePipeline(model).transcribe(
                audio, word_timestamps=True, batch_size=batch, language=language)
            words = _collect_words(segments, total, progress)
            engine = f"faster-whisper:{model_name}:batched{batch}"
        except Exception as e:  # noqa: BLE001
            print(f"Batched transcription failed ({e}); trying the one-at-a-time way.")
            words = None
    if words is None:
        segments, info = model.transcribe(audio, word_timestamps=True, vad_filter=True, language=language)
        words = _collect_words(segments, total, progress)
        engine = f"faster-whisper:{model_name}"

    print(f"Transcribed {fmt_mmss(total)} with {engine} in {time.time() - started:.0f}s.")
    data = {"duration": total, "language": language or info.language,
            "segments": sentence_segments(words), "words": words, "engine": engine}
    out_json.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def _collect_words(segments, total, progress):
    words = []
    for s in segments:
        for w in s.words or []:
            t = w.word.strip()
            if t:
                words.append({"w": t, "s": round(w.start, 2), "e": round(w.end, 2)})
        progress(min(99, s.end / max(total, 1) * 100), f"Transcribed {fmt_mmss(s.end)} of {fmt_mmss(total)}")
    words.sort(key=lambda w: w["s"])
    return words


# --------------------------------------------------------------------------- 2. pick moments
PICK_PROMPT = """You are an expert short-form video editor for a YouTube creator.
Below is the timestamped transcript of one long vlog ({duration}). Choose the {n} best moments
to turn into stand-alone YouTube Shorts.

A great moment:
- makes sense with no context from the rest of the vlog
- grabs attention in the first 2 seconds (a reaction, a surprising line, a question, a strong claim)
- has a payoff or ending (a punchline, reveal, tip, or conclusion)
- is between {min_len} and {max_len} seconds long
- does not overlap with any other moment you pick

Start each moment at the beginning of a sentence and end it after a complete sentence.
Spread picks across the whole vlog when quality is similar.

Return ONLY a JSON array of exactly {n} objects, best moment first, each with:
  "start": number (seconds),
  "end": number (seconds),
  "hook": on-screen hook text for the first seconds, max 6 words,
  "title": YouTube title, max 60 characters, no hashtags,
  "thumb_line1": thumbnail text line 1, max 3 words,
  "thumb_line2": thumbnail text line 2, max 3 words (the punchy part),
  "why": one short sentence on why this moment works,
  "hashtags": array of 3 hashtags without the # sign

TRANSCRIPT
{transcript}
"""


# Current Flash models, newest first (checked October 2026).
FALLBACK_MODELS = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash", "gemini-2.5-flash"]
BUSY_WAITS = [15, 45]  # seconds to wait before another round when every model is busy


def gemini_error_kind(e):
    """Sort a Gemini error into: busy, limit, missing, bad_key or other."""
    code = getattr(e, "code", None)
    msg = str(e).lower()
    if code in (500, 502, 503, 504) or any(k in msg for k in ("unavailable", "overloaded", "high demand",
                                                               "deadline", "internal error", "timed out")):
        return "busy"
    if code == 429 or "resource_exhausted" in msg or "quota" in msg:
        return "limit"
    if code == 404 or "not found" in msg or "not_found" in msg or "is not supported" in msg:
        return "missing"
    if code in (401, 403) or "api key" in msg or "api_key" in msg or "permission" in msg:
        return "bad_key"
    return "other"


def pick_moments(transcript, n, progress=lambda pct, msg: None):
    from google import genai

    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is missing. Add it to the .env file (see README).")
    lines = [f"[{s['s']:.1f}-{s['e']:.1f}] {s['text']}" for s in transcript["segments"]]
    prompt = PICK_PROMPT.format(
        duration=fmt_mmss(transcript["duration"]), n=n, min_len=MIN_LEN + 5, max_len=MAX_LEN,
        transcript="\n".join(lines),
    )
    progress(10, "Reading the whole transcript")
    client = genai.Client(api_key=key)
    # Try the model from .env first, then the other current models.
    # Gemini sometimes answers "busy" (503) or "limit reached" (429): wait and retry,
    # then move on to the next model, instead of failing the whole job.
    wanted = os.getenv("GEMINI_MODEL") or FALLBACK_MODELS[0]
    candidates = [wanted] + [m for m in FALLBACK_MODELS if m != wanted]
    config = {"response_mime_type": "application/json", "temperature": 0.4,
              "automatic_function_calling": {"disable": True}}
    resp, problems = None, []
    # Each round tries every model once; if they were all busy, wait a bit and go again.
    for wait in [0] + BUSY_WAITS:
        if wait:
            progress(10, f"Gemini is busy, trying again in {wait} seconds")
            time.sleep(wait)
        retry_later = []
        for model in candidates:
            try:
                resp = client.models.generate_content(model=model, contents=prompt, config=config)
                break
            except Exception as e:  # noqa: BLE001
                kind = gemini_error_kind(e)
                if kind == "bad_key":
                    raise RuntimeError("Gemini refused the API key. Check GEMINI_API_KEY in the .env file "
                                       "(create a fresh key at https://aistudio.google.com/apikey).") from e
                if kind == "other":
                    raise
                problems.append(kind)
                print(f"Gemini model '{model}': {kind}.")
                if kind == "busy":
                    retry_later.append(model)  # missing models and used-up limits aren't retried
                if model != candidates[-1]:
                    progress(10, "Trying another Gemini model")
        if resp is not None or not retry_later:
            break
        candidates = retry_later
    if resp is None:
        if "busy" in problems:
            raise RuntimeError("Gemini is overloaded right now (this is on Google's side). Your transcript is "
                               "saved, so just click Make my Shorts again in a few minutes with the same video; "
                               "it will skip straight to finding moments.")
        if "limit" in problems:
            raise RuntimeError("Gemini's free usage limit is used up for now. Try again in a while (or tomorrow) "
                               "with the same video; the transcript is saved, so it won't be redone.")
        raise RuntimeError("None of the Gemini models are available to this API key. "
                           "Put a current Flash model name in GEMINI_MODEL in .env.")
    progress(80, "Choosing the best moments")
    text = re.sub(r"^```(?:json)?|```$", "", (resp.text or "").strip(), flags=re.M).strip()
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", text, flags=re.S)  # salvage a list wrapped in extra words
        if not m:
            raise RuntimeError("Gemini's answer wasn't in the expected format. Click Make my Shorts again.")
        raw = json.loads(m.group(0))
    if isinstance(raw, dict):
        raw = next((v for v in raw.values() if isinstance(v, list)), [])
    return clean_moments(raw, transcript, n)


def clean_moments(raw, transcript, n):
    """Snap AI picks to real word boundaries, enforce length, drop overlaps."""
    words = transcript["words"]
    dur = transcript["duration"]
    picked = []
    for m in raw:
        try:
            s, e = float(m["start"]), float(m["end"])
        except (KeyError, TypeError, ValueError):
            continue
        inside = [w for w in words if w["s"] >= s - 0.4 and w["e"] <= e + 0.6]
        if not inside:
            continue
        s = max(0.0, inside[0]["s"] - 0.15)
        # stay under MAX_LEN, ending on a finished word
        inside = [w for w in inside if w["e"] - s <= MAX_LEN - 0.4] or inside[:1]
        e = min(dur, inside[-1]["e"] + 0.35)
        if e - s < MIN_LEN:
            continue
        if any(not (e <= p["start"] or s >= p["end"]) for p in picked):
            continue
        picked.append({
            "start": round(s, 2), "end": round(e, 2),
            "hook": str(m.get("hook", ""))[:60],
            "title": str(m.get("title", "New Short"))[:90],
            "thumb_line1": str(m.get("thumb_line1", ""))[:30],
            "thumb_line2": str(m.get("thumb_line2", ""))[:30],
            "why": str(m.get("why", "")),
            "hashtags": [re.sub(r"[^\w]", "", h) for h in m.get("hashtags", [])][:5],
        })
        if len(picked) == n:
            break
    if not picked:
        raise RuntimeError("Couldn't find usable moments. Try a different vlog or fewer Shorts.")
    return picked


# --------------------------------------------------------------------------- 3. render
def face_center_x(video_path, start, end, width):
    """Median horizontal position of the main face during the clip (None if no face).

    If face finding isn't available or fails for any reason, return None so the
    Short is simply cropped from the centre instead of the whole job failing.
    """
    try:
        return _face_center_x(video_path, start, end)
    except Exception as e:  # noqa: BLE001
        print(f"Face finding skipped ({e}); cropping from the centre.")
        return None


def _face_center_x(video_path, start, end):
    try:
        import cv2
    except ImportError:
        return None
    if not hasattr(cv2, "CascadeClassifier"):  # OpenCV 5 moved it out of the main package
        return None
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    cap = cv2.VideoCapture(str(video_path))
    xs, t = [], start
    while t < end:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        t += 1.0
        if not ok:
            continue
        scale = 640 / frame.shape[1]
        small = cv2.resize(frame, None, fx=scale, fy=scale)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(40, 40))
        if len(faces):
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            xs.append((x + w / 2) / scale)
    cap.release()
    return statistics.median(xs) if len(xs) >= 2 else None


def ass_time(t):
    t = max(0.0, t)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def ass_escape(text):
    return text.replace("\\", "").replace("{", "(").replace("}", ")")


CAPTION_STYLES = {
    # name: (fontsize, borderstyle, outline, shadow, outline colour, uppercase)
    "bold":  (92, 1, 7, 2, "&H00000000", True),
    "clean": (70, 1, 2, 4, "&H00000000", False),
    "boxed": (74, 3, 14, 0, "&H40000000", False),
}
YELLOW = "&H000AD6FF&"  # #FFD60A in ASS (BGR) order


def build_ass(words, clip_start, clip_end, hook, style, path):
    fs, bs, ol, sh, oc, upper = CAPTION_STYLES.get(style, CAPTION_STYLES["bold"])
    font = caption_font_name(Path(path).parent / "fonts")
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {OUT_W}
PlayResY: {OUT_H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},{fs},&H00FFFFFF,&H00FFFFFF,{oc},&H80000000,-1,0,0,0,100,100,0,0,{bs},{ol},{sh},2,80,80,560,1
Style: Hook,{font},66,&H00111111,&H00111111,&H00FFFFFF,&H00FFFFFF,-1,0,0,0,100,100,0,0,3,18,0,8,90,90,200,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    clip = [w for w in words if w["s"] >= clip_start - 0.05 and w["e"] <= clip_end + 0.05]
    chunks = [clip[i:i + 3] for i in range(0, len(clip), 3)]
    for ci, chunk in enumerate(chunks):
        nxt = chunks[ci + 1][0]["s"] if ci + 1 < len(chunks) else None
        for wi, w in enumerate(chunk):
            start = w["s"] - clip_start
            if wi + 1 < len(chunk):
                end = chunk[wi + 1]["s"] - clip_start
            else:
                end = w["e"] - clip_start
                if nxt is not None and nxt - w["e"] < 0.6:
                    end = nxt - clip_start
            if end <= start:
                end = start + 0.08
            parts = []
            for j, x in enumerate(chunk):
                t = ass_escape(x["w"].upper() if upper else x["w"])
                parts.append(f"{{\\c{YELLOW}}}{t}{{\\c&H00FFFFFF&}}" if j == wi else t)
            lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Cap,,0,0,0,,{' '.join(parts)}")
    if hook:
        lines.append(f"Dialogue: 1,{ass_time(0)},{ass_time(2.8)},Hook,,0,0,0,,{ass_escape(hook)}")
    Path(path).write_text(head + "\n".join(lines) + "\n", encoding="utf-8")


def crop_filter(meta, center_x):
    w, h = meta["width"], meta["height"]
    if w / h <= 9 / 16 + 0.01:  # already vertical
        return (f"scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease:flags=lanczos,"
                f"pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2:black")
    cw = int(h * 9 / 16) // 2 * 2
    cx = center_x if center_x is not None else w / 2
    x = int(min(max(cx - cw / 2, 0), w - cw)) // 2 * 2
    return f"crop={cw}:{h}:{x}:0,scale={OUT_W}:{OUT_H}:flags=lanczos"


def prepare_job_fonts(job_dir):
    """libass reads fonts from a folder next to the captions (avoids Windows path issues)."""
    dst = Path(job_dir) / "fonts"
    dst.mkdir(exist_ok=True)
    if FONTS_DIR.exists():
        for f in FONTS_DIR.iterdir():
            if f.suffix.lower() in (".ttf", ".otf") and not (dst / f.name).exists():
                shutil.copy(f, dst / f.name)
    if not any(f.suffix.lower() in (".ttf", ".otf") for f in dst.iterdir()):
        fallback = find_font_file()  # e.g. Arial Bold on a Mac
        if fallback:
            shutil.copy(fallback, dst / Path(fallback).name)


def render_short(video_path, meta, moment, words, idx, style, job_dir):
    job_dir = Path(job_dir)
    s, e = moment["start"], moment["end"]
    cx = face_center_x(video_path, s, e, meta["width"])
    ass_name = f"captions_{idx}.ass"
    build_ass(words, s, e, moment.get("hook", ""), style, job_dir / ass_name)
    out_name = f"short_{idx}.mp4"
    vf = f"{crop_filter(meta, cx)},subtitles={ass_name}:fontsdir=fonts"
    run([
        ffmpeg_exe(), "-y", "-ss", f"{s:.2f}", "-i", str(Path(video_path).resolve()), "-t", f"{e - s:.2f}",
        "-vf", vf,
        "-c:v", "libx264", "-preset", os.getenv("X264_PRESET", "medium"), "-crf", "18",
        "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out_name,
    ], cwd=job_dir)
    return out_name, cx


# --------------------------------------------------------------------------- 4. thumbnail
def make_thumbnail(video_path, meta, moment, cx, idx, job_dir):
    from PIL import Image, ImageDraw, ImageFont

    job_dir = Path(job_dir)
    raw = job_dir / f"frame_{idx}.jpg"
    t = moment["start"] + (moment["end"] - moment["start"]) * 0.3
    run([ffmpeg_exe(), "-y", "-ss", f"{t:.2f}", "-i", str(Path(video_path).resolve()),
         "-frames:v", "1", "-vf", crop_filter(meta, cx), "-q:v", "2", str(raw)])
    img = Image.open(raw).convert("RGB")

    # darken the lower part so text pops
    shade = Image.new("L", (1, OUT_H))
    for y in range(OUT_H):
        shade.putpixel((0, y), int(max(0, (y - OUT_H * 0.45) / (OUT_H * 0.55)) * 190))
    black = Image.new("RGB", img.size, (0, 0, 0))
    img = Image.composite(black, img, shade.resize(img.size))

    d = ImageDraw.Draw(img)
    font_path = find_font_file()

    def font(size):
        return ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default()

    def fit(text, max_size):
        size = max_size
        while size > 50:
            f = font(size)
            if d.textlength(text, font=f) <= OUT_W - 140:
                return f
            size -= 6
        return font(size)

    l1 = (moment.get("thumb_line1") or "").upper()
    l2 = (moment.get("thumb_line2") or moment.get("hook") or "").upper()
    y = OUT_H - 560
    if l1:
        f1 = fit(l1, 140)
        d.text((70, y), l1, font=f1, fill="white", stroke_width=8, stroke_fill="black")
        y += f1.size + 30
    if l2:
        f2 = fit(l2, 150)
        tw = d.textlength(l2, font=f2)
        d.rounded_rectangle((52, y - 10, 70 + tw + 22, y + f2.size + 26), radius=18, fill=(255, 214, 10))
        d.text((70, y), l2, font=f2, fill=(17, 17, 17))
    name = f"thumb_{idx}.jpg"
    img.save(job_dir / name, quality=92)
    raw.unlink(missing_ok=True)
    return name
