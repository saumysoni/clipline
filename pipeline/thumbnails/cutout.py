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


# A cut-out only looks good if the background remover was sure where the edge is. Measured on real
# frames: clean cut-outs (a plate, a dish) had soft < 0.2, solidity > 0.9, ragged < 1.3; messy ones
# (a dark dish, innards, a building) had soft > 1.5, solidity < 0.8, ragged > 2.4. Messy ones become
# photo cards instead. Faces are exempt (hair is ragged by nature) but get a smoothed outline.
MAX_SOFT = 0.5      # half-transparent pixels per solid pixel: the remover wasn't sure where the edge is
MIN_SOLIDITY = 0.85  # area / area of its convex hull: low means bites and spikes
MAX_RAGGED = 2.0    # perimeter^2 / (4 pi area): 1 for a circle, high for a frayed edge


def edge_quality(alpha, mask):
    """(soft, solidity, ragged) of a cut-out mask; see the limits above."""
    from scipy import ndimage
    from skimage.morphology import convex_hull_image

    area = max(1, mask.sum())
    soft = ((alpha > 0.1) & (alpha < 0.9)).sum() / area
    solidity = area / max(1, convex_hull_image(mask).sum())
    edge = mask ^ ndimage.binary_erosion(mask)
    ragged = edge.sum() ** 2 / (4 * np.pi * area)
    return soft, solidity, ragged


def smooth_mask(mask):
    """Round off jagged edges and drop small loose bits, so the sticker outline drawn around it is tidy."""
    from scipy import ndimage

    sigma = max(1.5, min(mask.shape) * 0.006)
    smooth = ndimage.gaussian_filter(mask.astype(np.float32), sigma) > 0.5
    labels, count = ndimage.label(smooth)
    if count > 1:
        sizes = ndimage.sum(smooth, labels, range(1, count + 1))
        smooth = np.isin(labels, 1 + np.flatnonzero(sizes >= 0.05 * sizes.max()))
    return ndimage.binary_fill_holes(smooth) if smooth.any() else mask


def cut_out(img, keep_point=None, strict=True):
    """RGBA cut-out of the main subject, cleaned up, or None if it didn't work well.
    strict: also refuse cut-outs with messy edges (for objects; faces pass strict=False)."""
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
    if strict:
        soft, solidity, ragged = edge_quality(a, mask)
        if soft > MAX_SOFT or solidity < MIN_SOLIDITY or ragged > MAX_RAGGED:
            return None
    mask = smooth_mask(mask)
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


def face_cutout(img, face_box=None):
    """The creator from the chest up, cut out. Crops around the face first so other people
    and the background confuse the cut-out less. face_box (from the AI, 0-1000 scale) says where the
    creator's face is; without it the face finder guesses (and can pick a wrong "face" on a wall)."""
    if face_box:
        y0, x0, y1, x1 = face_box
        face = (int(x0 / 1000 * img.width), int(y0 / 1000 * img.height),
                max(1, int((x1 - x0) / 1000 * img.width)), max(1, int((y1 - y0) / 1000 * img.height)))
    else:
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
    cut = cut_out(crop, keep_point=point, strict=False)
    return cut, crop


def face_size(img):
    """Width of the largest face as a share of the frame width (0 if none)."""
    face, _ = find_faces(img)
    return face[2] / img.width if face else 0.0
