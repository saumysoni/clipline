"""
Clipline pipeline: one long vlog in, N finished vertical Shorts out.

Steps
  1. transcribe()      faster-whisper, word-level timestamps (runs on your computer, free)
  2. pick_moments()    Gemini or OpenAI (AI_PROVIDER) reads the transcript and picks the best moments
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
HOOK_STYLES = ("curiosity", "bold", "story")
HOOK_RULE = ("Hooks may tease or reframe, in the creator's tone, but every fact in them (numbers, money, places, "
             "events) must come from what is said in the moment. Never invent anything.")


def _numbers(text):
    """Numbers in a text, written the same way ("5 ,000" and "5,000" both become 5000)."""
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", re.sub(r"\s+,", ",", text or ""))}


def _hook_dict(value):
    """Hook options as {style: text}, whatever shape the AI used: an object, a list holding an object
    (seen from OpenAI), a list of {"style", "text"} objects, or a plain list of texts."""
    if isinstance(value, dict):
        return {str(k).strip().lower(): v for k, v in value.items()}
    out = {}
    if isinstance(value, list):
        for k, item in enumerate(value):
            if isinstance(item, dict):
                if "text" in item or "hook" in item:
                    out[str(item.get("style") or item.get("type") or HOOK_STYLES[k % 3]).lower()] = \
                        item.get("text") or item.get("hook")
                else:
                    out.update(_hook_dict(item))
            elif isinstance(item, str) and k < len(HOOK_STYLES):
                out[HOOK_STYLES[k]] = item
    elif isinstance(value, str):
        out["custom"] = value
    return out


def hook_fields(raw, said="", fallback=None):
    """The hook options from an AI answer, keeping only honest ones: a hook with a number that isn't
    said in the moment ("I lost $2,000" from a clip that never says it) is dropped.
    Returns hooks (style -> text), hook_style, hook (the chosen text) and hook_mode."""
    raw = raw if isinstance(raw, dict) else {}
    fb = fallback or {}
    said_numbers = _numbers(said)
    hooks = {}
    offered = _hook_dict(raw.get("hooks"))
    single = " ".join(str(raw.get("hook") or "").split())[:60]
    for style, text in [*((k, offered.get(k)) for k in HOOK_STYLES), ("custom", single)]:
        text = " ".join(str(text or "").split())[:60]
        if not text or text in hooks.values():
            continue
        if _numbers(text) - said_numbers:
            print(f"  Dropped the {style} hook {text!r}: it has a number that isn't said in the moment.")
            continue
        hooks[style] = text
    if not hooks and fb.get("hooks"):
        return {k: fb[k] for k in ("hooks", "hook_style", "hook", "hook_mode") if k in fb}
    pick = str(raw.get("hook_pick", "")).lower()
    style = pick if pick in hooks else next(iter(hooks), "custom")
    hook = hooks.get(style) or fb.get("hook", "")
    return {"hooks": hooks, "hook_style": style, "hook": hook, "hook_mode": "text" if hook else "none"}


HOOK_PROMPT = """You write on-screen hooks for a YouTube Short: the text shown in the first seconds that makes
people keep watching. Write three, each max 6 words:
  "curiosity": makes them need to know what happens,
  "bold": a strong claim or reaction,
  "story": sets up the story.
{hook_rule}
{note}Return ONLY a JSON object: {{"hooks": {{"curiosity": ..., "bold": ..., "story": ...}},
  "hook_pick": the strongest: "curiosity", "bold" or "story"}}

Short title: {title}
{context}WHAT IS SAID IN THIS SHORT
{said}
"""


def rewrite_hooks(transcript, moment, note="", context=None):
    """Three fresh hook options for a Short, optionally nudged by the creator ("funnier")."""
    said = said_between(transcript, moment["start"], moment["end"])
    raw = ai_json(HOOK_PROMPT.format(
        hook_rule=HOOK_RULE, title=moment.get("title", ""), said=said[:4000] or "(no talking in this Short)",
        note=f"The creator asks: {note.strip()[:300]}\n" if note.strip() else "",
        context=vlog_context_block(context)), temperature=0.8)
    out = hook_fields(raw, said)
    if not out.get("hooks"):
        raise RuntimeError("Couldn't write new hooks that stick to what's said in this Short. Try again, "
                           "or type your own hook.")
    return out


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
{hook_rule}

Return ONLY a JSON array of exactly {n} objects, best moment first, each with:
  "start": number (seconds),
  "end": number (seconds),
  "hooks": three on-screen hook options for the first seconds, each max 6 words:
           {{"curiosity": makes them need to know what happens, "bold": a strong claim or reaction,
             "story": sets up the story}},
  "hook_pick": which of the three is strongest: "curiosity", "bold" or "story",
  "title": YouTube title, max 60 characters, no hashtags,
  "thumb_line1": thumbnail text line 1, max 3 words,
  "thumb_line2": thumbnail text line 2, max 3 words (the punchy part),
  "why": one short sentence on why this moment works,
  "hashtags": array of 3 hashtags without the # sign

{context}TRANSCRIPT
{transcript}
"""


# Current Flash models, newest first (checked October 2026).
FALLBACK_MODELS = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash", "gemini-2.5-flash"]
OPENAI_FALLBACK_MODELS = ["gpt-5.4-mini", "gpt-5-mini", "gpt-4.1-mini"]
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


def openai_error_kind(e):
    """Sort an OpenAI error into: busy, limit, no_credit, missing, bad_key or other."""
    code = getattr(e, "status_code", None)
    msg = str(e).lower()
    name = type(e).__name__
    if (code is not None and code >= 500) or name in ("APIConnectionError", "APITimeoutError"):
        return "busy"
    if "insufficient_quota" in msg:
        return "no_credit"  # out of prepaid credit, waiting won't help
    if code == 429:
        return "limit"
    if code == 404 or "model_not_found" in msg or "does not exist" in msg:
        return "missing"
    if code in (401, 403):
        return "bad_key"
    return "other"


def vlog_context_block(context):
    """The creator's own title/description/tags, as extra guidance for the AI."""
    if not context:
        return ""
    parts = []
    if context.get("title"):
        parts.append(f"Title: {context['title'].strip()}")
    if context.get("description"):
        parts.append("Description:\n" + context["description"].strip()[:3000])
    if context.get("tags"):
        parts.append("Tags: " + ", ".join(context["tags"][:30]))
    if not parts:
        return ""
    return ("ABOUT THIS VLOG (written by the creator)\n" + "\n".join(parts) + "\n\n"
            "Use this to understand what the vlog is about, to spell names of people and places correctly "
            "(the transcript may misspell them), and to write titles and hooks in the creator's own tone. "
            "Never copy links, sponsor codes or timestamps from the description.\n\n")


def image_part(data, mime_type="image/jpeg"):
    """An image for ai_json(), in a form every provider understands."""
    return {"image": data, "mime_type": mime_type}


def ai_provider():
    return (os.getenv("AI_PROVIDER") or "gemini").strip().lower()


def ai_json(contents, progress=lambda pct, msg: None, temperature=0.4, busy_hint=""):
    """Ask the AI chosen by AI_PROVIDER in .env (gemini or openai) for JSON.

    `contents` is a string, or a list of strings and image_part()s. Returns the parsed JSON.
    """
    provider = ai_provider()
    if provider == "openai":
        return openai_json(contents, progress, temperature, busy_hint)
    if provider != "gemini":
        raise RuntimeError(f"AI_PROVIDER in .env is '{provider}', which Clipline doesn't know. "
                           "Set it to gemini or openai and restart.")
    return gemini_json(contents, progress, temperature, busy_hint)


def ask_models(name, candidates, call, error_kind, fatal, progress, busy_hint, busy_msg, limit_msg, none_msg):
    """Run call(model) on each model in turn and return the first answer.

    Busy models are retried in rounds (waits in BUSY_WAITS), missing or limited models are skipped,
    and errors listed in `fatal` stop at once with that message.
    """
    resp, problems = None, []
    # Each round tries every model once; if they were all busy, wait a bit and go again.
    for wait in [0] + BUSY_WAITS:
        if wait:
            progress(10, f"{name} is busy, trying again in {wait} seconds")
            time.sleep(wait)
        retry_later = []
        for model in candidates:
            try:
                resp = call(model)
                break
            except Exception as e:  # noqa: BLE001
                kind = error_kind(e)
                if kind in fatal:
                    raise RuntimeError(fatal[kind]) from e
                if kind == "other":
                    raise
                problems.append(kind)
                print(f"{name} model '{model}': {kind}.")
                if kind == "busy":
                    retry_later.append(model)  # missing models and used-up limits aren't retried
                if model != candidates[-1]:
                    progress(10, f"Trying another {name} model")
        if resp is not None or not retry_later:
            break
        candidates = retry_later
    if resp is None:
        if "busy" in problems:
            raise RuntimeError(busy_msg + busy_hint)
        if "limit" in problems:
            raise RuntimeError(limit_msg + busy_hint)
        raise RuntimeError(none_msg)
    return resp


def parse_ai_json(text, name):
    text = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"[\[{].*[\]}]", text, flags=re.S)  # salvage JSON wrapped in extra words
        if not m:
            raise RuntimeError(f"{name}'s answer wasn't in the expected format. Please try again.")
        return json.loads(m.group(0))


def candidate_models(env_name, fallbacks):
    wanted = os.getenv(env_name) or fallbacks[0]
    return [wanted] + [m for m in fallbacks if m != wanted]


def gemini_json(contents, progress=lambda pct, msg: None, temperature=0.4, busy_hint=""):
    """Ask Gemini for JSON, trying the model from .env first and then the other current models.

    Gemini sometimes answers "busy" (503) or "limit reached" (429): busy models are retried in rounds
    (waits in BUSY_WAITS), missing or limited models are skipped. `contents` may be a string or a list
    of strings and image_part()s. Returns the parsed JSON (dict or list).
    """
    from google import genai
    from google.genai import types

    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is missing. Add it to the .env file (see README).")
    client = genai.Client(api_key=key)
    if isinstance(contents, list):
        contents = [types.Part.from_bytes(data=c["image"], mime_type=c["mime_type"]) if isinstance(c, dict)
                    else c for c in contents]
    config = {"response_mime_type": "application/json", "temperature": temperature,
              "automatic_function_calling": {"disable": True}}
    resp = ask_models(
        "Gemini", candidate_models("GEMINI_MODEL", FALLBACK_MODELS),
        lambda model: client.models.generate_content(model=model, contents=contents, config=config),
        gemini_error_kind,
        {"bad_key": "Gemini refused the API key. Check GEMINI_API_KEY in the .env file "
                    "(create a fresh key at https://aistudio.google.com/apikey)."},
        progress, busy_hint,
        busy_msg="Gemini is overloaded right now (this is on Google's side). ",
        limit_msg="Gemini's free usage limit is used up for now. Try again in a while (or tomorrow). ",
        none_msg="None of the Gemini models are available to this API key. "
                 "Put a current Flash model name in GEMINI_MODEL in .env.")
    return parse_ai_json(resp.text, "Gemini")


def openai_json(contents, progress=lambda pct, msg: None, temperature=0.4, busy_hint=""):
    """Ask OpenAI for JSON, trying OPENAI_MODEL first and then the other current models (same retry
    rules as gemini_json()). OpenAI's JSON mode only returns objects, so a requested list comes back
    wrapped in an object; callers already accept that.
    """
    import base64

    from openai import OpenAI

    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is missing. Add it to the .env file (see README), "
                           "or set AI_PROVIDER=gemini.")
    client = OpenAI(api_key=key, max_retries=0, timeout=300)
    parts = []
    for c in contents if isinstance(contents, list) else [contents]:
        if isinstance(c, dict):
            url = f"data:{c['mime_type']};base64," + base64.b64encode(c["image"]).decode()
            parts.append({"type": "image_url", "image_url": {"url": url}})
        else:
            parts.append({"type": "text", "text": c})
    messages = [
        {"role": "system", "content": "Reply with one JSON object and nothing else. If you are asked for "
                                      "a list, put it in the object as {\"items\": [...]}."},
        {"role": "user", "content": parts},
    ]
    no_temperature = set()  # reasoning models only accept their default temperature

    def call(model):
        args = {"model": model, "messages": messages, "response_format": {"type": "json_object"}}
        if model not in no_temperature:
            args["temperature"] = temperature
        try:
            return client.chat.completions.create(**args)
        except Exception as e:  # noqa: BLE001
            if "temperature" in str(e).lower() and "temperature" in args:
                no_temperature.add(model)
                args.pop("temperature")
                return client.chat.completions.create(**args)
            raise

    resp = ask_models(
        "OpenAI", candidate_models("OPENAI_MODEL", OPENAI_FALLBACK_MODELS), call, openai_error_kind,
        {"bad_key": "OpenAI refused the API key. Check OPENAI_API_KEY in the .env file "
                    "(create a key at https://platform.openai.com/api-keys).",
         "no_credit": "Your OpenAI account has no credit left. Add credit at "
                      "https://platform.openai.com/settings/organization/billing and try again."},
        progress, busy_hint,
        busy_msg="OpenAI is overloaded right now (this is on OpenAI's side). ",
        limit_msg="OpenAI's rate limit was reached. Wait a minute and try again. ",
        none_msg="None of the OpenAI models are available to this API key. "
                 "Put a current model name in OPENAI_MODEL in .env.")
    return parse_ai_json(resp.choices[0].message.content, "OpenAI")


def _moment_prompt(transcript, n, context, extra):
    lines = [f"[{s['s']:.1f}-{s['e']:.1f}] {s['text']}" for s in transcript["segments"]]
    return PICK_PROMPT.format(
        hook_rule=HOOK_RULE, duration=fmt_mmss(transcript["duration"]), n=n, min_len=MIN_LEN + 5, max_len=MAX_LEN,
        transcript="\n".join(lines), context=vlog_context_block(context) + (extra and extra + "\n"),
    )


def creator_wishes(taken=(), rejected=(), note=""):
    """Prompt lines for what the creator already chose, didn't like, or asked for."""
    span = lambda m: f"{m['start']:.1f}-{m['end']:.1f}s"  # noqa: E731
    extra = ""
    if taken:
        extra += "ALREADY USED, never overlap these: " + ", ".join(span(m) for m in taken) + "\n"
    if rejected:
        extra += ("THE CREATOR DIDN'T LIKE these picks, choose something different: "
                  + ", ".join(span(m) for m in rejected) + "\n")
    if note.strip():
        extra += ("WHAT THE CREATOR WANTS (follow it closely; if they mention a time like 3:20, the moment "
                  f"must include that time): {note.strip()[:1000]}\n")
    return extra


def _as_list(raw):
    if isinstance(raw, dict):
        raw = next((v for v in raw.values() if isinstance(v, list)), [])
    return raw if isinstance(raw, list) else []


def pick_moments(transcript, n, progress=lambda pct, msg: None, context=None, note="", taken=()):
    """The n best moments. `note` is the creator's instructions; `taken` are moments the creator
    chose themselves (never overlapped)."""
    if n <= 0:
        return []
    progress(10, "Reading the whole transcript")
    raw = ai_json(_moment_prompt(transcript, n + (2 if taken else 0), context, creator_wishes(taken, (), note)),
                  progress, busy_hint=(
        "Your transcript is saved, so just click Make my Shorts again in a few minutes with the same "
        "video; it will skip straight to finding moments."))
    progress(80, "Choosing the best moments")
    try:
        picked = clean_moments(_as_list(raw), transcript, n + (2 if taken else 0))
    except RuntimeError:
        if taken:  # the creator's own moments still make a job worth finishing
            return []
        raise
    kept = [m for m in picked if not any(overlaps(m, t) for t in taken)]
    if len(kept) < len(picked):
        print(f"  {len(picked) - len(kept)} of those dropped, they overlap your must-have moments.")
    return kept[:n]


def clean_moments(raw, transcript, n):
    """Snap AI picks to real word boundaries, enforce length, drop overlaps.

    Prints each suggestion and what happened to it, so a short count can be explained."""
    words = transcript["words"]
    dur = transcript["duration"]
    picked = []
    print(f"AI suggested {len(raw)} moment(s) for {n} Short(s):")

    def log(m, why):
        try:
            span = f"{fmt_mmss(float(m['start']))}-{fmt_mmss(float(m['end']))}"
        except (KeyError, TypeError, ValueError):
            span = "?"
        title = m.get("title", "") if isinstance(m, dict) else ""
        print(f"  {span} {title!r}: {why}")

    for m in raw:
        if len(picked) == n:
            log(m, "not needed, already have enough")
            continue
        try:
            s, e = float(m["start"]), float(m["end"])
        except (KeyError, TypeError, ValueError):
            log(m, "dropped, no usable start/end times")
            continue
        inside = [w for w in words if w["s"] >= s - 0.4 and w["e"] <= e + 0.6]
        if not inside:
            log(m, "dropped, nobody speaks in it")
            continue
        s = max(0.0, inside[0]["s"] - 0.15)
        # stay under MAX_LEN, ending on a finished word
        inside = [w for w in inside if w["e"] - s <= MAX_LEN - 0.4] or inside[:1]
        e = min(dur, inside[-1]["e"] + 0.35)
        if e - s < MIN_LEN:
            log(m, f"dropped, only {e - s:.0f}s from first to last spoken word (needs {MIN_LEN}s)")
            continue
        if any(not (e <= p["start"] or s >= p["end"]) for p in picked):
            log(m, "dropped, overlaps a moment already chosen")
            continue
        log(m, f"kept as {fmt_mmss(s)}-{fmt_mmss(e)}")
        picked.append({
            "start": round(s, 2), "end": round(e, 2),
            **hook_fields(m, said_between(transcript, s, e)),
            "title": str(m.get("title", "New Short"))[:90],
            "thumb_line1": str(m.get("thumb_line1", ""))[:30],
            "thumb_line2": str(m.get("thumb_line2", ""))[:30],
            "why": str(m.get("why", "")),
            "hashtags": [re.sub(r"[^\w]", "", h) for h in m.get("hashtags", [])][:5],
        })
    if not picked:
        raise RuntimeError("Couldn't find usable moments. Try a different vlog or fewer Shorts.")
    return picked


def overlaps(a, b):
    return a["start"] < b["end"] and b["start"] < a["end"]


REDO_PROMPT = """You are an expert short-form video editor for a YouTube creator. The creator wants to change
one Short made from their vlog ({duration} long).

{current}{wishes}
Decide what they want:
- "adjust": they want THIS Short changed (longer, shorter, a set length, start earlier, end later, include
  what comes before or after). Keep what's in it now and move the start and end. Follow a requested length
  exactly, even if part of it has no talking.
- "new": they want a different moment. Pick moments that make sense on their own, grab attention in the
  first 2 seconds and have a payoff.
Moments are {min_len}-{max_len} seconds long unless the creator asks for another length (never over 180).
Start at the beginning of a sentence and end after a complete sentence where there is talking.
{hook_rule}

Return ONLY a JSON object:
{{"change": "adjust" or "new",
  "options": up to 3 moments, best first, each {{"start": seconds, "end": seconds,
    "hooks": {{"curiosity": ..., "bold": ..., "story": ...}} three on-screen hooks, max 6 words each,
    "hook_pick": the strongest of the three, "title": YouTube title, max 60 characters, no hashtags,
    "thumb_line1": max 3 words, "thumb_line2": max 3 words (the punchy part),
    "why": one short sentence, "hashtags": array of 3 hashtags without the # sign}}}}

{context}TRANSCRIPT
{transcript}
"""

LENGTH_RE = re.compile(r"(\d+(?:\.\d+)?)\s*-?\s*(s|secs?|seconds?|m|mins?|minutes?)\b", re.I)


def requested_length(note):
    """The length in seconds a creator asks for ("make it 30 sec", "1 minute"), or None.
    With several lengths ("this 13 sec clip, make it 30 sec"), the one after make it/to/into/be wins."""
    note = (note or "").lower()
    if re.search(r"half (a|of a) minute", note):
        return 30.0
    found = []
    for m in LENGTH_RE.finditer(note):
        sec = float(m.group(1)) * (60 if m.group(2).startswith("m") else 1)
        aimed = re.search(r"\b(make it|to|into|be|as|about|around|of)\s+(a\s+)?$", note[:m.start()].rstrip() + " ")
        found.append((bool(aimed), sec))
    if not found:
        return 60.0 if re.search(r"\b(a|one) minute\b", note) else None
    aimed = [sec for ok, sec in found if ok]
    return aimed[0] if aimed else found[-1][1]


def stretch(current, target, duration, taken):
    """The current Short made `target` seconds long: the end moves first, then the start, never into
    another Short or past the video. Shortening keeps the start."""
    s, e = current["start"], current["end"]
    target = max(MANUAL_MIN, min(target, MANUAL_MAX, duration))
    if e - s >= target:
        return s, s + target
    after = min([t["start"] for t in taken if t["start"] >= e - 0.5] + [duration])
    before = max([t["end"] for t in taken if t["end"] <= s + 0.5] + [0.0])
    e2 = min(after, s + target)
    return max(before, e2 - target), e2


def repick_moment(transcript, taken, rejected, note="", progress=lambda pct, msg: None, context=None,
                  current=None):
    """A new moment for a Short the creator wants changed: adjusted ("make it 30 seconds") or different.

    `taken` are the other Shorts (never overlapped), `rejected` the moments already tried for this Short,
    `note` what the creator asked for (may be empty), `current` the Short as it is now (None for a new one).
    When the creator asked for something, the answer follows it even through parts without talking,
    and a requested length is honoured without the AI if needed. Raises only if nothing fits.
    """
    span = lambda m: f"{m['start']:.1f}-{m['end']:.1f}s"  # noqa: E731
    cur = current if current and not current.get("pending") else None
    lines = [f"[{x['s']:.1f}-{x['e']:.1f}] {x['text']}" for x in transcript["segments"]]
    prompt = REDO_PROMPT.format(
        hook_rule=HOOK_RULE, duration=fmt_mmss(transcript["duration"]), min_len=MIN_LEN + 5, max_len=MAX_LEN,
        current=(f"THIS SHORT NOW: {span(cur)} ({cur['end'] - cur['start']:.0f}s), titled {cur.get('title', '')!r}\n"
                 if cur else "This is a NEW Short, so pick a moment (\"new\").\n"),
        wishes=creator_wishes(taken, [r for r in rejected if not cur or not overlaps(r, cur)], note)
        or "The creator just wants something better.\n",
        context=vlog_context_block(context), transcript="\n".join(lines))
    progress(20, "Reading the transcript again")
    raw, change = {}, "new"
    try:
        raw = ai_json(prompt, progress)
        change = str(raw.get("change", "new")).lower() if isinstance(raw, dict) else "new"
    except RuntimeError:
        if not (note.strip() and cur and requested_length(note)):
            raise  # nothing to fall back on
        print("AI unavailable; making the requested length without it.")
    options = _as_list(raw)
    progress(60, "Choosing the moment")
    free = lambda m: not any(overlaps(m, t) for t in taken)  # noqa: E731

    # A different moment, held to the usual standard (enough talking, sensible length).
    if change != "adjust":
        try:
            strict = [m for m in clean_moments(options, transcript, 3) if free(m)]
        except RuntimeError:
            strict = []
        fresh = [m for m in strict if not any(overlaps(m, r) for r in rejected)]
        if fresh:
            return fresh[0]
        if strict and note.strip():
            return strict[0]

    # The creator asked for something: follow the AI's times as given, even through silence.
    if note.strip() or change == "adjust":
        for o in options:
            try:
                s, e = snap_moment(transcript, float(o["start"]), float(o["end"]))
            except (KeyError, TypeError, ValueError, RuntimeError) as err:
                print(f"  AI option {o!r:.80}: unusable ({err})")
                continue
            m = {"start": s, "end": e, "manual": True,
                 **moment_text(o, cur if change == "adjust" else None, said_between(transcript, s, e), s)}
            if free(m):
                print(f"  Following the creator's request: {fmt_mmss(s)}-{fmt_mmss(e)} ({change}).")
                return m
            print(f"  AI option {fmt_mmss(s)}-{fmt_mmss(e)}: overlaps another Short")

    # Still nothing, but they asked for a length: stretch or trim this Short ourselves.
    target = requested_length(note) if cur else None
    if target:
        s, e = snap_moment(transcript, *stretch(cur, target, transcript["duration"], taken))
        got = e - s
        why = (f"Made {got:.0f} seconds long, as you asked." if abs(got - target) < 2 else
               f"Made {got:.0f} seconds long, the most that fits next to your other Shorts and the video's ends.")
        print(f"  Stretched to {fmt_mmss(s)}-{fmt_mmss(e)} for the requested {target:.0f}s.")
        return {"start": s, "end": e, "manual": True, **moment_text({"why": why}, cur, said_between(transcript, s, e), s)}

    raise RuntimeError("Couldn't find a moment that matches. Use Choose on the video to mark the start and end "
                       "yourself, or describe it differently.")


MANUAL_MIN, MANUAL_MAX = 5, 180  # a moment the creator times themselves (YouTube allows Shorts up to 3 minutes)

TEXT_PROMPT = """You are an expert short-form video editor for a YouTube creator. The creator chose this moment
of their vlog ({start} to {end}) for a YouTube Short. Write the text for it.
{note}
{hook_rule}
Return ONLY a JSON object with:
  "hooks": three on-screen hook options for the first seconds, each max 6 words:
           {{"curiosity": makes them need to know what happens, "bold": a strong claim or reaction,
             "story": sets up the story}},
  "hook_pick": which of the three is strongest: "curiosity", "bold" or "story",
  "title": YouTube title, max 60 characters, no hashtags,
  "thumb_line1": thumbnail text line 1, max 3 words,
  "thumb_line2": thumbnail text line 2, max 3 words (the punchy part),
  "why": one short sentence on why this moment works,
  "hashtags": array of 3 hashtags without the # sign

{context}WHAT IS SAID IN THIS MOMENT
{said}
"""


def parse_time(text):
    """Seconds from what a creator types: 2:10, 1:02:10, 130 or 130.5. None if it isn't a time."""
    text = str(text or "").strip()
    if not re.fullmatch(r"\d+(:\d{1,2}){0,2}(\.\d+)?", text):
        return None
    sec = 0.0
    for part in text.split(":"):
        sec = sec * 60 + float(part)
    return sec


def snap_moment(transcript, start, end):
    """Check a moment's times and nudge them so no word is cut in half. Returns (start, end).
    Speech isn't required: the creator may want a scene without talking."""
    dur = transcript["duration"]
    if start >= dur:
        raise RuntimeError(f"{fmt_mmss(start)} is past the end of the video ({fmt_mmss(dur)}). Check the times.")
    start, end = max(0.0, start), min(end, dur)
    if end - start < MANUAL_MIN:
        raise RuntimeError(f"The moment from {fmt_mmss(start)} to {fmt_mmss(end)} is too short. "
                           f"Make it at least {MANUAL_MIN} seconds.")
    if end - start > MANUAL_MAX:
        raise RuntimeError(f"The moment from {fmt_mmss(start)} to {fmt_mmss(end)} is longer than 3 minutes, "
                           "the most YouTube allows for a Short. Shorten it.")
    words = transcript["words"]
    cut = next((w for w in words if w["s"] < start < w["e"]), None)
    if cut:
        start = cut["s"]
    cut = next((w for w in words if w["s"] < end < w["e"]), None)
    if cut:
        end = min(dur, cut["e"] + 0.2)
    return round(max(0.0, start - 0.1), 2), round(end, 2)


def moment_text(raw, fallback=None, said="", start=0.0):
    """Title, hook, thumbnail lines, why and hashtags from an AI answer, filling gaps from `fallback`
    (e.g. the Short being adjusted) or the words said, so a moment always has usable text."""
    raw = raw if isinstance(raw, dict) else {}
    fb = fallback or {}
    pick = lambda k: raw.get(k) or fb.get(k) or ""  # noqa: E731
    first = " ".join(said.split()[:8])
    return {
        **hook_fields(raw, said, fb),
        "title": str(pick("title") or first or f"Short from {fmt_mmss(start)}")[:90],
        "thumb_line1": str(pick("thumb_line1"))[:30],
        "thumb_line2": str(pick("thumb_line2"))[:30],
        "why": str(raw.get("why") or fb.get("why") or "You picked this moment."),
        "hashtags": [re.sub(r"[^\w]", "", str(h)) for h in (raw.get("hashtags") or fb.get("hashtags") or [])
                     if str(h).strip()][:5],
    }


def said_between(transcript, start, end):
    return " ".join(w["w"] for w in transcript["words"] if start <= w["s"] < end)


def manual_moment(transcript, start, end, note="", progress=lambda pct, msg: None, context=None):
    """A moment the creator timed themselves. The AI only writes its text; if that fails, simple
    text is used, so a creator's own pick never fails because of the AI."""
    start, end = snap_moment(transcript, start, end)
    said = said_between(transcript, start, end)
    progress(30, "Writing the title and hook")
    raw = {}
    try:
        raw = ai_json(TEXT_PROMPT.format(
            hook_rule=HOOK_RULE, start=fmt_mmss(start), end=fmt_mmss(end), said=said[:4000] or "(no speech in this moment)",
            note=f"What the creator says about it: {note.strip()[:500]}\n" if note.strip() else "",
            context=vlog_context_block(context)), progress, temperature=0.5)
    except Exception as e:  # noqa: BLE001
        print(f"Couldn't write text for the creator's moment ({e}); using simple text.")
    return {"start": start, "end": end, "manual": True, **moment_text(raw, None, said, start)}


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


def without_emoji(text):
    """Text without emoji and other pictographs: the caption and thumbnail fonts have none, so they'd
    show as empty boxes. (They're fine in titles and descriptions, which YouTube displays itself.)"""
    import unicodedata
    out = "".join(c for c in (text or "") if not (
        ord(c) >= 0x1F000 or unicodedata.category(c) in ("So", "Cs") or ord(c) in (0xFE0F, 0x200D, 0x20E3)))
    return re.sub(r"\s+([?!.,])", r"\1", " ".join(out.split()))


def ass_escape(text):
    return without_emoji(text).replace("\\", "").replace("{", "(").replace("}", ")")


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


def make_preview(video_path, out_path):
    """A small copy of the whole vlog for choosing scenes in the browser.

    The original may be 4K, HEVC or HDR, which many browsers can't play (or load slowly);
    this small H.264 copy (480p, 24 fps, ~8 MB a minute) plays everywhere, with a keyframe every second
    so scrubbing is quick.
    """
    out_path = Path(out_path)
    tmp = out_path.with_name(out_path.stem + ".part.mp4")
    # -hwaccel auto decodes with the machine's video hardware when it has some (reading 4K/HEVC/HDR is the
    # slow part) and falls back to the processor by itself, so this works the same on any server.
    run([ffmpeg_exe(), "-y", "-hwaccel", "auto", "-i", str(Path(video_path).resolve()),
         "-vf", "fps=24,scale='if(gt(iw,ih),-2,480)':'if(gt(iw,ih),480,-2)'",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "33", "-g", "24", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "96k", "-ac", "2", "-movflags", "+faststart", str(tmp)])
    tmp.replace(out_path)
    return out_path.name


def render_short(video_path, meta, moment, words, idx, style, job_dir, cx="find"):
    """Cut, reframe and caption one Short. Pass `cx` (from an earlier render of the same moment) to
    skip finding the face again, e.g. when only the hook changed."""
    job_dir = Path(job_dir)
    s, e = moment["start"], moment["end"]
    if cx == "find":
        cx = face_center_x(video_path, s, e, meta["width"])
    ass_name = f"captions_{idx}.ass"
    hook = moment.get("hook", "") if moment.get("hook_mode", "text") != "none" else ""
    build_ass(words, s, e, hook, style, job_dir / ass_name)
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
def make_thumbnail(video_path, meta, moment, cx, idx, job_dir, words=None, context=None):
    """Collage-style thumbnail (see thumbnails.py); the simple style if that fails or THUMB_STYLE=simple."""
    if os.getenv("THUMB_STYLE", "collage").lower() != "simple":
        try:
            import thumbnails
            return thumbnails.make_collage_thumbnail(video_path, moment, idx, job_dir, words, context)
        except Exception as e:  # noqa: BLE001
            print(f"Collage thumbnail failed ({e}); using the simple style.")
    return make_simple_thumbnail(video_path, meta, moment, cx, idx, job_dir)


def hook_to_lines(hook):
    """A hook split over the thumbnail's two lines as evenly as possible (line 2 is the big block)."""
    text = re.sub(r"\s+([?!.,])", r"\1", without_emoji(hook))
    words = text.split()
    if len(words) <= 2:
        return "", text
    k = min(range(1, len(words)), key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))))
    return " ".join(words[:k]), " ".join(words[k:])


def retext_thumbnail(video_path, meta, moment, cx, num, job_dir):
    """The Short's thumbnail with new text (moment's thumb_line1/2) as thumb_<num>.jpg. A collage reuses
    its saved frames and layout (no AI, no new frames); otherwise the simple style is drawn again."""
    work = moment.get("thumb_work") or "thumbwork_" + re.sub(r"\D", "", moment.get("thumb", ""))
    if (Path(job_dir) / work / "plan.json").exists():
        try:
            import thumbnails
            return thumbnails.retext(job_dir, work, moment.get("thumb_line1", ""), moment.get("thumb_line2", ""),
                                     f"thumb_{num}.jpg"), work
        except Exception as e:  # noqa: BLE001
            print(f"Couldn't redraw the collage thumbnail ({e}); using the simple style.")
    return make_simple_thumbnail(video_path, meta, moment, cx, num, job_dir), None


def make_simple_thumbnail(video_path, meta, moment, cx, idx, job_dir):
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

    l1 = without_emoji(moment.get("thumb_line1") or "").upper()
    l2 = without_emoji(moment.get("thumb_line2") or moment.get("hook") or "").upper()
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
