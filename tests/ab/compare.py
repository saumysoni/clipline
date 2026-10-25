"""
A/B comparisons of Pit Crew's own options on the same input, so a setting is chosen from numbers, not guesses:

  encoder    X264_PRESET ultrafast / veryfast (default) / medium: time to make one Short, file size, and quality
             against medium (SSIM, 1.0 = identical; above 0.98 nobody can tell on a phone).
  captions   the bold (default) / clean / boxed caption styles: time and size of the same Short.
  looks      the Frame (default) / Duotone thumbnails: time to draw, file size (YouTube's limit is 2 MB) and how
             much the headline stands out from the picture behind it (contrast ratio; 4.5+ is easy to read).
  slots      JOB_SLOTS 1 vs 2 on this machine: how long 2 vlogs take to finish, made one after the other or
             together, and the memory it took.
  whisper    (only where the speech model is downloaded, i.e. on the server) int8 vs float32 and batch sizes:
             time to transcribe the same audio.

The AI and transcription are the test fakes, so no keys or quota are used. Run from the clipline folder:

    python -m tests.ab.compare                    # everything (a few minutes)
    python -m tests.ab.compare encoder looks      # only some
Prints a table and writes ab-<date>.md / .json to tests/ab/results (or the temp folder if that isn't writable).
"""
import os

os.environ["PITCREW_REAL_MEDIA"] = "1"

from tests import fakes as F  # noqa: E402  (first: clean settings, fakes, throwaway folders)

import json  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
from datetime import datetime  # noqa: E402
from pathlib import Path  # noqa: E402

RESULTS = []


def row(test, variant, **numbers):
    RESULTS.append({"test": test, "variant": variant, **numbers})
    print(f"  {test:9} {variant:22} " + "  ".join(f"{k}={v}" for k, v in numbers.items()), flush=True)


def workdir(source):
    d = Path(tempfile.mkdtemp(prefix="pitcrew-ab-", dir=F.TMP))  # removed with the rest when the run ends
    shutil.copy(source, d / "source.mp4")
    import pipeline
    pipeline.prepare_job_fonts(d)
    return d


def ssim(a, b):
    from pipeline.ffmpeg import ffmpeg_exe
    out = subprocess.run([ffmpeg_exe(), "-i", str(a), "-i", str(b), "-lavfi", "ssim", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    m = re.search(r"All:([\d.]+)", out)
    return round(float(m.group(1)), 4) if m else None


def moment():
    return {"start": 20.0, "end": 50.0, "hook": "Wait for the ending", "hook_mode": "text", "title": "A/B test Short",
            "thumb_line1": "WE GOT", "thumb_line2": "LOST"}


def encoder(source, tr):
    import pipeline
    meta = pipeline.probe(source)
    d = workdir(source)
    files = {}
    for preset in ("medium", "veryfast", "ultrafast"):
        os.environ["X264_PRESET"] = preset
        t = time.time()
        name, _ = pipeline.render_short(d / "source.mp4", meta, moment(), tr["words"], len(files) + 1, "bold", d, cx=None)
        files[preset] = (d / name, time.time() - t)
    os.environ["X264_PRESET"] = "ultrafast"
    for preset, (f, secs) in files.items():
        row("encoder", preset + (" (default)" if preset == "veryfast" else ""), seconds=round(secs, 1),
            mb=round(f.stat().st_size / 1e6, 2), ssim_vs_medium=ssim(f, files["medium"][0]))


def captions(source, tr):
    import pipeline
    meta = pipeline.probe(source)
    d = workdir(source)
    for k, style in enumerate(("bold", "clean", "boxed"), 1):
        t = time.time()
        name, _ = pipeline.render_short(d / "source.mp4", meta, moment(), tr["words"], k, style, d, cx=None)
        row("captions", style + (" (default)" if style == "bold" else ""), seconds=round(time.time() - t, 1),
            mb=round((d / name).stat().st_size / 1e6, 2))


def _contrast(img, box):
    """WCAG contrast between the headline's white and the picture right around it."""
    from PIL import ImageStat
    lum = lambda v: ((v / 255 + 0.055) / 1.055) ** 2.4 if v / 255 > 0.03928 else v / 255 / 12.92  # noqa: E731
    region = img.convert("L").crop(box)
    px = sorted(region.getdata())
    bright, dark = px[int(len(px) * 0.98)], px[int(len(px) * 0.4)]
    a, b = lum(bright) + 0.05, lum(dark) + 0.05
    return round(max(a, b) / min(a, b), 1), round(ImageStat.Stat(region).mean[0])


def looks(source, tr):
    from PIL import Image
    from pipeline.thumbnails import layout
    from pipeline.thumbnails.frames import sample_frames
    d = workdir(source)
    frames = sample_frames(d / "source.mp4", 20, 50, d / "work")
    for look in layout.LOOKS:
        pl = {"frame": 3, "focus": [250, 350, 650, 650], "line1": "WE GOT", "line2": "LOST", "accent": "#FFD60A",
              "look": look}
        t = time.time()
        img = layout.compose(frames, dict(pl))
        secs = time.time() - t
        out = d / f"{look}.jpg"
        layout.save(img.convert("RGB"), out)
        top = layout.text_spot(img.convert("RGBA"), pl["line1"], pl["line2"], layout.subject_span(frames[3], pl["focus"]))[0]
        box = (60, 120, 1020, 700) if top else (60, 1200, 1020, 1690)
        ratio, _ = _contrast(Image.open(out), box)
        row("looks", look + (" (default)" if look == layout.LOOKS[0] else ""), seconds=round(secs, 2),
            kb=round(out.stat().st_size / 1024), contrast=ratio)


def slots(source, tr):
    """2 vlogs of 1 Short each, with JOB_SLOTS 1 and 2."""
    import web.job_queue as Q
    c = F.client(F.new_user())
    c2 = F.client(F.new_user())  # another creator: one vlog per creator runs at a time anyway
    for n in (1, 2):
        Q.SLOTS = n
        rss0 = _peak_mb()
        t = time.time()
        ids = []
        for cl in (c, c2):
            up = F.upload(cl, source)
            ids.append((cl, cl.post("/api/start", data={"upload": up, "count": "1"}).get_json()["id"]))
        for cl, jid in ids:
            F.wait_ready(cl, jid, timeout=900)
        row("slots", f"JOB_SLOTS={n}", seconds_for_2=round(time.time() - t, 1), cores=os.cpu_count(),
            peak_mb=max(rss0, _peak_mb()))
    Q.SLOTS = 2


def _peak_mb():
    try:
        for line in open("/proc/self/status"):
            if line.startswith("VmHWM:"):
                return round(int(line.split()[1]) / 1024)
    except OSError:
        pass
    import resource
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 if sys.platform != "darwin" else 1024 ** 2))


def whisper(source, tr):
    if os.getenv("PITCREW_HF_HOME"):  # where the server keeps the speech model (deploy/test.sh passes it)
        os.environ["HF_HOME"] = os.environ["PITCREW_HF_HOME"]
    try:
        from faster_whisper import WhisperModel
        from pipeline.transcribe import load_audio
    except Exception as e:  # noqa: BLE001
        row("whisper", "skipped", reason=type(e).__name__)
        return
    audio = load_audio(source)[: 16000 * 60]
    for compute, batch in (("int8", 8), ("int8", 0), ("float32", 8)):
        try:
            model = WhisperModel(os.getenv("WHISPER_MODEL", "small"), device="cpu", compute_type=compute,
                                 cpu_threads=os.cpu_count() or 2, local_files_only=True)
        except Exception as e:  # noqa: BLE001  (the model isn't downloaded here)
            row("whisper", "skipped", reason=str(e)[:60])
            return
        t = time.time()
        if batch:
            from faster_whisper import BatchedInferencePipeline
            segs, _ = BatchedInferencePipeline(model).transcribe(audio, batch_size=batch, language="en")
        else:
            segs, _ = model.transcribe(audio, language="en")
        list(segs)
        row("whisper", f"{compute} batch={batch}", seconds_per_min_audio=round(time.time() - t, 1))


TESTS = {"encoder": encoder, "captions": captions, "looks": looks, "slots": slots, "whisper": whisper}


def main(names):
    F.install()
    F.app()
    source = F.test_video(90, "640x360", plain=True)
    tr = F.transcript_for(90)
    print(f"A/B on {os.cpu_count()} cores, {sys.platform}:")
    for name in names or TESTS:
        TESTS[name](source, tr)
    out = Path(__file__).resolve().parent / "results"
    try:
        out.mkdir(exist_ok=True)
        (out / ".write-test").touch()
        (out / ".write-test").unlink()
    except OSError:
        out = Path(tempfile.gettempdir())
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    (out / f"ab-{stamp}.json").write_text(json.dumps(RESULTS, indent=1), encoding="utf-8")
    lines = [f"# A/B results {stamp} ({os.cpu_count()} cores, {sys.platform})", "", "| Test | Variant | Numbers |",
             "|---|---|---|"]
    lines += [f"| {r['test']} | {r['variant']} | " + ", ".join(f"{k} {v}" for k, v in r.items()
                                                                 if k not in ("test", "variant")) + " |" for r in RESULTS]
    (out / f"ab-{stamp}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nSaved: {out / f'ab-{stamp}.md'}")


if __name__ == "__main__":
    main(sys.argv[1:])
