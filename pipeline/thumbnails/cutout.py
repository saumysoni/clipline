"""
Thumbnails, step 3: cutting the creator and objects out of frames (rembg, runs on the processor).
"""
import os

import numpy as np
from PIL import Image, ImageFilter

from pipeline.thumbnails.frames import find_faces


_REMBG = {}


def rembg_session():
    """Background remover, loaded once per process. None if rembg isn't installed."""
    name = os.getenv("THUMB_CUTOUT_MODEL", "isnet-general-use")
    if name not in _REMBG:
        try:
            from rembg import new_session
            _REMBG[name] = new_session(name)
        except Exception as e:  # noqa: BLE001
            print(f"Cut-outs unavailable ({e}); using photo cards instead.")
            _REMBG[name] = None
    return _REMBG[name]


def cut_out(img, keep_point=None):
    """RGBA cut-out of the main subject, cleaned up, or None if it didn't work well."""
    sess = rembg_session()
    if sess is None:
        return None
    from rembg import remove
    from scipy import ndimage

    rgba = remove(img, session=sess)
    a = np.asarray(rgba.getchannel("A"), dtype=np.float32) / 255.0
    solid = a > 0.5
    # Shrink the mask a little before splitting it into separate blobs, so things that only touch the
    # subject through a thin bridge (someone else's arm, a seat edge) come apart; then grow it back.
    r = max(2, int(min(solid.shape) * 0.012))
    core = ndimage.binary_erosion(solid, iterations=r)
    labels, count = ndimage.label(core if core.any() else solid)
    if count == 0:
        return None
    if keep_point and 0 <= keep_point[1] < labels.shape[0] and 0 <= keep_point[0] < labels.shape[1] \
            and labels[keep_point[1], keep_point[0]]:
        keep = labels[keep_point[1], keep_point[0]]
    else:
        keep = 1 + int(np.argmax(ndimage.sum(labels > 0, labels, range(1, count + 1))))
    mask = ndimage.binary_dilation(labels == keep, iterations=r + 1) & solid
    mask = ndimage.binary_fill_holes(mask)
    coverage = mask.mean()
    if not 0.04 <= coverage <= 0.92:  # nothing found, or nothing removed
        return None
    alpha = Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2))
    out = rgba.convert("RGB").convert("RGBA")
    out.putalpha(alpha)
    return out.crop(out.getbbox())


def crop_box(img, box, pad=0.08):
    y0, x0, y1, x1 = box
    w, h = img.size
    bw, bh = (x1 - x0) / 1000 * w, (y1 - y0) / 1000 * h
    l = max(0, int(x0 / 1000 * w - bw * pad))
    t = max(0, int(y0 / 1000 * h - bh * pad))
    r = min(w, int(x1 / 1000 * w + bw * pad))
    b = min(h, int(y1 / 1000 * h + bh * pad))
    return img.crop((l, t, r, b))


def face_cutout(img):
    """The creator from the chest up, cut out. Crops around the face first so other people
    and the background confuse the cut-out less."""
    face, _ = find_faces(img)
    if face:
        x, y, w, h = face
        # head and shoulders only: about 1.2 face-widths either side, so people sitting next to
        # the creator (a driver, a friend) don't get pulled into the cut-out
        box = (max(0, int(x - 1.2 * w)), max(0, int(y - 0.9 * h)),
               min(img.width, int(x + 2.2 * w)), min(img.height, int(y + 4.2 * h)))
        crop = img.crop(box)
        point = (x + w // 2 - box[0], y + h // 2 - box[1])
    else:
        crop, point = img, None
    cut = cut_out(crop, keep_point=point)
    return cut, crop
