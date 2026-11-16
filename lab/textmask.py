"""Font- and palette-agnostic text mask: bright pixel with a p/4 drop shadow."""

import numpy as np


def shadow_mask(rgb: np.ndarray, k: int, bright: int = 72) -> np.ndarray:
    """Pixels with a drop shadow (about p/4 per channel) at (+k, +k)"""
    h, w, _ = rgb.shape
    a = rgb[: h - k, : w - k].astype(np.int16)
    b = rgb[k:, k:].astype(np.int16)
    am = a.max(axis=2)
    ok = am >= bright
    # per channel: b ~ a/4 (tolerance for blend / rounding / remapped palettes)
    # (upper bound per channel from the max channel: a pack can remap text
    # colour but the shadow keeps the vanilla colour / 4)
    lo = a // 12 - 3
    hi = (am[..., None] * 7) // 20 + 4
    ok &= ((b >= lo) & (b <= hi)).all(axis=2)
    bm = b.max(axis=2)
    ok &= bm * 20 >= am * 3 - 60
    m = np.zeros((h, w), bool)
    m[: h - k, : w - k] = ok
    return m


def scale_votes(rgb: np.ndarray, ks: range = range(1, 7)) -> dict[int, int]:
    return {k: int(shadow_mask(rgb, k).sum()) for k in ks}
