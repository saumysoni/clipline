"""
The designed thumbnail from start to finish (frames -> AI plan -> layout in a look), and redrawing one
with new text or in another look from its saved thumbwork_N/ folder (no AI, no new frames).
"""
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from pathlib import Path

from PIL import Image

from pipeline.thumbnails.frames import sample_frames
from pipeline.thumbnails.layout import compose, save
from pipeline.thumbnails.plan import AI_DEADLINE, fresh_accent, plan, plan_without_ai, upgrade_plan


_ACCENT_LOCK = threading.Lock()  # thumbnails made side by side must not pick the same colour


def redraw(job_dir, work_name, out_name, **changes):
    """Redraw a thumbnail from the frames and plan saved when it was made (no AI, no new frames),
    with `changes` applied to the plan (new text: line1/line2, another look: look)."""
    work = Path(job_dir) / work_name
    pl = upgrade_plan(json.loads((work / "plan.json").read_text(encoding="utf-8")))
    paths = sorted(work.glob("frame_*.jpg"), key=lambda f: int(f.stem.split("_")[1]))
    frames = [Image.open(f).convert("RGB") for f in paths]
    pl.update(changes)
    pl = upgrade_plan(pl)  # tidies new text too
    save(compose(frames, pl), Path(job_dir) / out_name)
    (work / "plan.json").write_text(json.dumps(pl, indent=1), encoding="utf-8")
    return out_name


def retext(job_dir, work_name, line1, line2, out_name):
    """Redraw a thumbnail with new text."""
    return redraw(job_dir, work_name, out_name, line1=line1, line2=line2)


def make_designed_thumbnail(video_path, moment, idx, job_dir, words=None, context=None):
    job_dir = Path(job_dir)
    work = job_dir / f"thumbwork_{idx}"
    frames = sample_frames(video_path, moment["start"], moment["end"], work)
    # The AI gets AI_DEADLINE seconds in all; after that the thumbnail is planned without it, so one
    # request that never answers can't hold up the whole job (it once hung forever on "Thumbnail 2 of 6").
    pool = ThreadPoolExecutor(1)
    try:
        pl = pool.submit(plan, frames, moment, words, context).result(timeout=AI_DEADLINE)
    except FuturesTimeout:
        print(f"Thumbnail planning took over {AI_DEADLINE}s; planning without AI.")
        pl = plan_without_ai(frames, moment)
    except Exception as e:  # noqa: BLE001  (no key, Gemini busy, odd answer...)
        print(f"Thumbnail planning without AI ({e}).")
        pl = plan_without_ai(frames, moment)
    finally:
        pool.shutdown(wait=False)
    with _ACCENT_LOCK:  # choose the colour and save the plan at once, so the next thumbnail sees it
        pl["accent"] = fresh_accent(job_dir, work.name, pl["accent"])
        (work / "plan.json").write_text(json.dumps(pl, indent=1), encoding="utf-8")
    img = compose(frames, pl)
    name = f"thumb_{idx}.jpg"
    save(img, job_dir / name)
    (work / "plan.json").write_text(json.dumps(pl, indent=1), encoding="utf-8")
    moment["thumb_look"], moment["thumb_work"] = pl["look"], work.name  # so the page can show and change it
    return name
