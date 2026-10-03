"""
The collage thumbnail from start to finish (frames -> plan -> cut-outs -> layout), and redrawing
one with new text from its saved thumbwork_N/ folder (no AI, no new frames).
"""
from pathlib import Path

from PIL import Image

from pipeline.thumbnails.frames import sample_frames
from pipeline.thumbnails.layout import compose, save
from pipeline.thumbnails.plan import fresh_accent, plan, plan_without_ai


def retext(job_dir, work_name, line1, line2, out_name):
    """Redraw a collage thumbnail with new text, from the frames and layout saved when it was made."""
    import json

    work = Path(job_dir) / work_name
    pl = json.loads((work / "plan.json").read_text(encoding="utf-8"))
    paths = sorted(work.glob("frame_*.jpg"), key=lambda f: int(f.stem.split("_")[1]))
    frames = [Image.open(f).convert("RGB") for f in paths]
    pl.update(line1=line1, line2=line2)
    save(compose(frames, pl), Path(job_dir) / out_name)
    (work / "plan.json").write_text(json.dumps(pl, indent=1), encoding="utf-8")
    return out_name


def make_collage_thumbnail(video_path, moment, idx, job_dir, words=None, context=None):
    job_dir = Path(job_dir)
    work = job_dir / f"thumbwork_{idx}"
    frames = sample_frames(video_path, moment["start"], moment["end"], work)
    try:
        pl = plan(frames, moment, words, context)
    except Exception as e:  # noqa: BLE001  (no key, Gemini busy, odd answer...)
        print(f"Thumbnail planning without AI ({e}).")
        pl = plan_without_ai(frames, moment)
    pl["accent"] = fresh_accent(job_dir, work.name, pl["accent"])
    img = compose(frames, pl)
    name = f"thumb_{idx}.jpg"
    save(img, job_dir / name)
    (work / "plan.json").write_text(__import__("json").dumps(pl, indent=1), encoding="utf-8")
    return name
