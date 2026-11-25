"""Name regions of the parsed rows, and the model crop of a row band."""

from dataclasses import dataclass

import cv2
import numpy as np

from prism.overlay.tabcap.reader.front.guiscale import Array
from prism.overlay.tabcap.reader.front.parse import PRow, shade_of

H = 20  # model input height: rows y-k .. y+9k at 2 px per GUI px


@dataclass
class NameRegion:
    prow: PRow
    x0: int
    x1: int
    mask: Array  # bool 8k x (x1 - x0)


def name_region(rgb: Array, p: PRow, merge_gap: float = 4.0) -> NameRegion | None:
    """Name word plus the following same-colour words (wide-spaced fonts split
    a name into several words)"""
    if p.name is None:
        return None
    k = p.row.k
    i = next(i for i, w in enumerate(p.words) if w is p.name)
    x1 = p.name.x1
    for w in p.words[i + 1 :]:
        if (
            w.x0 - x1 >= merge_gap * k
            or max(abs(a - b) for a, b in zip(w.color, p.name.color)) > 24
        ):
            break
        x1 = w.x1
    band = rgb[p.row.y : p.row.y + 8 * k, p.name.x0 : x1]
    m = shade_of(band, p.name.color)
    cols = np.flatnonzero(m.any(0))
    if len(cols) == 0:
        return None
    return NameRegion(
        p,
        p.name.x0 + int(cols[0]),
        p.name.x0 + int(cols[-1]) + 1,
        m[:, cols[0] : cols[-1] + 1],
    )


def regions_of(rgb: Array, prows: list[PRow], k: int) -> list[NameRegion]:
    """Name regions; drop duplicates (the same text found by two row chains)"""
    out: list[NameRegion] = []
    for p in prows:
        r = name_region(rgb, p)
        if r is None or r.x1 - r.x0 < 4 * k:
            continue
        y = p.row.y
        if any(abs(o.prow.row.y - y) <= k and o.x0 < r.x1 and r.x0 < o.x1 for o in out):
            continue
        out.append(r)
    return out


def norm_crop(rgb: Array, y: int, x0: int, x1: int, k: int) -> Array:
    """Row band (y = top of glyph area) -> uint8 H x W x 3 at 2 px per GUI px"""
    ya, yb = y - k, y + 9 * k
    xa, xb = max(0, x0 - 2 * k), min(rgb.shape[1], x1 + 2 * k)
    band = np.zeros((yb - ya, xb - xa, 3), np.uint8)
    sa, sb = max(0, ya), min(rgb.shape[0], yb)
    band[sa - ya : sb - ya] = rgb[sa:sb, xa:xb]
    w = max(4, round((xb - xa) * 2 / k))
    interp = cv2.INTER_AREA if k > 2 else cv2.INTER_NEAREST
    out: Array = cv2.resize(band, (w, H), interpolation=interp)
    return out
