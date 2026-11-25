"""Font- and palette-agnostic text mask: bright pixel with a p/4 drop shadow."""

import cv2
import numpy as np

from prism.overlay.tabcap.reader.front.guiscale import Array

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

    def __init__(self, rgb: Array) -> None:
        self.rgb = rgb
        r, g, b = cv2.split(np.ascontiguousarray(rgb))
        self.v: Array = cv2.max(cv2.max(r, g), b)
        self.hi: Array = cv2.LUT(self.v, _HI)
        self.lo: Array = cv2.LUT(self.v, _LO)
        self._masks: dict[int, Array] = {}

    def coarse(self, k: int) -> Array:
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

    def mask(self, k: int, coarse: Array | None = None) -> Array:
        """bool: the exact per-channel shadow test. Cached per k (the finders
        share one Shadow); do not change the returned array."""
        if coarse is None:
            if k not in self._masks:
                self._masks[k] = self._mask(k, self.coarse(k))
            return self._masks[k]
        return self._mask(k, coarse)

    def _mask(self, k: int, c: Array) -> Array:
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
