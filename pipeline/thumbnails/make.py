"""
Making a Short's thumbnail: the collage style (see collage.py), or the simple style if that fails
or THUMB_STYLE=simple. Also redraws a thumbnail with new text after a hook change.
"""
import os
import re
from pathlib import Path

from pipeline.thumbnails.simple import make_simple_thumbnail


def make_thumbnail(video_path, meta, moment, cx, idx, job_dir, words=None, context=None):
    """Collage-style thumbnail (see collage.py); the simple style if that fails or THUMB_STYLE=simple."""
    if os.getenv("THUMB_STYLE", "collage").lower() != "simple":
        try:
            from pipeline.thumbnails import collage
            return collage.make_collage_thumbnail(video_path, moment, idx, job_dir, words, context)
        except Exception as e:  # noqa: BLE001
            print(f"Collage thumbnail failed ({e}); using the simple style.")
    return make_simple_thumbnail(video_path, meta, moment, cx, idx, job_dir)


def retext_thumbnail(video_path, meta, moment, cx, num, job_dir):
    """The Short's thumbnail with new text (moment's thumb_line1/2) as thumb_<num>.jpg. A collage reuses
    its saved frames and layout (no AI, no new frames); otherwise the simple style is drawn again."""
    work = moment.get("thumb_work") or "thumbwork_" + re.sub(r"\D", "", moment.get("thumb", ""))
    if (Path(job_dir) / work / "plan.json").exists():
        try:
            from pipeline.thumbnails import collage
            return collage.retext(job_dir, work, moment.get("thumb_line1", ""), moment.get("thumb_line2", ""),
                                     f"thumb_{num}.jpg"), work
        except Exception as e:  # noqa: BLE001
            print(f"Couldn't redraw the collage thumbnail ({e}); using the simple style.")
    return make_simple_thumbnail(video_path, meta, moment, cx, num, job_dir), None


def relook_thumbnail(moment, num, job_dir, look):
    """The Short's collage thumbnail redrawn in another look (burst, scene or bold) as thumb_<num>.jpg,
    from its saved frames and plan: no AI, a few seconds. Returns (file name, work folder name)."""
    from pipeline.thumbnails import collage
    from pipeline.thumbnails.layout import LOOKS

    if look not in LOOKS:
        raise RuntimeError("That look doesn't exist. Choose Scene, Burst or Bold.")
    work = moment.get("thumb_work") or "thumbwork_" + re.sub(r"\D", "", moment.get("thumb", ""))
    if not (Path(job_dir) / work / "plan.json").exists():
        raise RuntimeError("This thumbnail was made in the simple style, so its look can't be changed. "
                           "Use Try again to remake the Short with a new thumbnail.")
    return collage.redraw(job_dir, work, f"thumb_{num}.jpg", look=look), work
