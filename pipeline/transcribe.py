"""
Transcription: every word of the vlog with exact timings (faster-whisper).

Runs the same on a laptop or a cloud server: an NVIDIA GPU is used automatically when present.
Tune with WHISPER_MODEL / WHISPER_DEVICE / WHISPER_BATCH_SIZE / WHISPER_THREADS / WHISPER_LANGUAGE.

Pit Crew is English-only for now: WHISPER_LANGUAGE defaults to "en", so the language is never guessed
(guessing once turned an English vlog into Welsh, and a Hinglish vlog into invented English). Set
WHISPER_LANGUAGE=auto to let Whisper work it out instead.
"""
import json
import os
import re
import subprocess
import time
from pathlib import Path

from pipeline.ffmpeg import ffmpeg_exe
from pipeline.text import fmt_mmss


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
    language = (os.getenv("WHISPER_LANGUAGE") or "en").strip().lower()
    language = None if language == "auto" else language
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

    words = drop_repeats(words)
    for w in words:  # a stuck letter ("sooooooo", "hmmmmmmm") is cut to two
        w["w"] = re.sub(r"(.)\1{3,}", r"\1\1", w["w"])
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


def drop_repeats(words, most=2):
    """Whisper sometimes gets stuck and repeats a phrase over a quiet or noisy stretch ("It's snowing
    everywhere" 40 times, "तीवा तीवा तीवा..."). Any phrase of 1-8 words said more than `most` times in a
    row is kept only `most` times."""
    key = lambda w: "".join(c for c in w["w"].lower() if c.isalnum())  # noqa: E731
    out, i = [], 0
    while i < len(words):
        best = None
        for n in range(1, 9):
            phrase = [key(w) for w in words[i:i + n]]
            if len(phrase) < n or not any(phrase):
                break
            reps = 1
            while [key(w) for w in words[i + reps * n:i + (reps + 1) * n]] == phrase:
                reps += 1
            if reps > most and (best is None or reps * n > best[0] * best[1]):
                best = (reps, n)
        if best:
            reps, n = best
            out += words[i:i + most * n]
            i += reps * n
        else:
            out.append(words[i])
            i += 1
    return out
