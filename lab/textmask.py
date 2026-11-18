"""Font- and palette-agnostic text mask: bright pixel with a p/4 drop shadow."""

import cv2
import numpy as np

from guiscale import gui_ks

BRIGHT = 72

# shadow test on the max channel, as lookup tables of the text value a:
# a >= BRIGHT, 20 b <= 7 a + 80, 20 b >= 3 a - 60
_A = np.arange(256)
_HI = np.clip((7 * _A + 80) // 20, 0, 255).astype(np.uint8)
_LO = np.clip(-((60 - 3 * _A) // 20), 0, 255).astype(np.uint8)  # ceil((3a-60)/20)
_HI[_A < BRIGHT] = 0
_LO[_A < BRIGHT] = 255


class Shadow:
    """Shadow masks of one image for any offset k, computed fast:
    a cheap max-channel test (cv2, uint8) on the whole image, then the
    per-channel test only on the pixels that pass it."""

    def __init__(self, rgb: np.ndarray) -> None:
        self.rgb = rgb
        r, g, b = cv2.split(np.ascontiguousarray(rgb))
        self.v = cv2.max(cv2.max(r, g), b)
        self.hi = cv2.LUT(self.v, _HI)
        self.lo = cv2.LUT(self.v, _LO)

    def coarse(self, k: int) -> np.ndarray:
        """uint8 0/255: max-channel shadow test at (+k, +k)"""
        h, w = self.v.shape
        b = self.v[k:, k:]
        m = np.zeros((h, w), np.uint8)
        ok = cv2.bitwise_and(
            cv2.compare(b, self.hi[: h - k, : w - k], cv2.CMP_LE),
            cv2.compare(b, self.lo[: h - k, : w - k], cv2.CMP_GE),
        )
        m[: h - k, : w - k] = ok
        return m

    def mask(self, k: int, coarse: np.ndarray | None = None) -> np.ndarray:
        """bool: the exact per-channel shadow test (same as shadow_mask)"""
        c = self.coarse(k) if coarse is None else coarse
        nz = cv2.findNonZero(c)
        if nz is None:
            return np.zeros(c.shape, bool)
        nz = nz.reshape(-1, 2)
        xs, ys = nz[:, 0], nz[:, 1]
        a = self.rgb[ys, xs].astype(np.int16)
        bb = self.rgb[ys + k, xs + k].astype(np.int16)
        am = a.max(axis=1, keepdims=True)
        ok = ((bb >= a // 12 - 3) & (bb <= (am * 7) // 20 + 4)).all(axis=1)
        m = np.zeros(c.shape, bool)
        m[ys[ok], xs[ok]] = True
        return m


def shadow_mask(rgb: np.ndarray, k: int, bright: int = BRIGHT) -> np.ndarray:
    """Pixels with a drop shadow (about p/4 per channel) at (+k, +k).
    Reference version (slow); Shadow.mask gives the same result."""
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


def scale_votes(rgb: np.ndarray, ks: range | None = None) -> dict[int, int]:
    return {k: int(shadow_mask(rgb, k).sum()) for k in (gui_ks(rgb) if ks is None else ks)}
