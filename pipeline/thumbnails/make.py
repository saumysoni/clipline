"""
Making a Short's thumbnail: the designed style (design.py: the AI's best frame in the Frame or Duotone
look), or the simple style if that fails or THUMB_STYLE=simple. Also redraws a thumbnail with new text
after a hook change, or in the other look.
"""
import os
import re
from pathlib import Path

from pipeline.thumbnails.simple import make_simple_thumbnail


def make_thumbnail(video_path, meta, moment, cx, idx, job_dir, words=None, context=None):
    """Designed thumbnail (see design.py); the simple style if that fails or THUMB_STYLE=simple."""
    if os.getenv("THUMB_STYLE", "designed").lower() != "simple":
        try:
            from pipeline.thumbnails import design
            return design.make_designed_thumbnail(video_path, moment, idx, job_dir, words, context)
        except Exception as e:  # noqa: BLE001
            print(f"Designed thumbnail failed ({e}); using the simple style.")
    return make_simple_thumbnail(video_path, meta, moment, cx, idx, job_dir)


def work_folder(moment):
    return moment.get("thumb_work") or "thumbwork_" + re.sub(r"\D", "", moment.get("thumb", ""))


def retext_thumbnail(video_path, meta, moment, cx, num, job_dir):
    """The Short's thumbnail with new text (moment's thumb_line1/2) as thumb_<num>.jpg. A designed one
    reuses its saved frames and plan (no AI, no new frames); otherwise the simple style is drawn again."""
    work = work_folder(moment)
    if (Path(job_dir) / work / "plan.json").exists():
        try:
            from pipeline.thumbnails import design
            return design.retext(job_dir, work, moment.get("thumb_line1", ""), moment.get("thumb_line2", ""),
                                 f"thumb_{num}.jpg"), work
        except Exception as e:  # noqa: BLE001
            print(f"Couldn't redraw the thumbnail ({e}); using the simple style.")
    return make_simple_thumbnail(video_path, meta, moment, cx, num, job_dir), None


def relook_thumbnail(moment, num, job_dir, look):
    """The Short's thumbnail redrawn in another look (frame or duotone) as thumb_<num>.jpg, from its saved
    frames and plan: no AI, about a second. Returns (file name, work folder name)."""
    from pipeline.thumbnails import design
    from pipeline.thumbnails.layout import LOOKS

    if look not in LOOKS:
        raise RuntimeError("That look doesn't exist. Choose Frame or Duotone.")
    work = work_folder(moment)
    if not (Path(job_dir) / work / "plan.json").exists():
        raise RuntimeError("This thumbnail was made in the simple style, so its look can't be changed. "
                           "Use Try again to remake the Short with a new thumbnail.")
    return design.redraw(job_dir, work, f"thumb_{num}.jpg", look=look), work
