"""Idea 1 POC: text mask from the predicted cell background.

cell = separator * (1 - 32/255) + 32 per channel (0x20FFFFFF over the panel).
Predict each cell pixel from the separator row above and the one below; a
pixel that fits neither prediction is not background (glyph or shadow).
Stats and pictures: bgmask_stats.py.
"""
import numpy as np

T = 18
BRIGHT = 72  # text has max channel >= 85; shadows are <= 63
A = 1 - 32 / 255


def predict(sep: np.ndarray) -> np.ndarray:
    return sep.astype(np.float32) * A + 32


def cell_diff(rgb, y, k, x0, x1):
    """8k x W: distance (max channel) of each cell pixel to the nearer of the
    two background predictions (from the separator above / below)"""
    H = rgb.shape[0]
    cell = rgb[y : y + 8 * k, x0:x1].astype(np.float32)
    up = predict(rgb[max(0, y - 1), x0:x1])
    dn = predict(rgb[min(H - 1, y + 8 * k), x0:x1])
    du = np.abs(cell - up[None]).max(axis=2)
    dd = np.abs(cell - dn[None]).max(axis=2)
    return np.minimum(du, dd)


def bg_mask(rgb, g, t=T, glyph_only=True):
    """Full-image bool mask of non-background pixels in the text part of
    each cell (after the head, before the ping icon)."""
    k = g.k
    m = np.zeros(rgb.shape[:2], bool)
    for x0, x1 in g.cols:
        a, b = x0 + 9 * k, x1 - 11 * k
        if b <= a:
            continue
        for y in g.tops:
            if y + 8 * k >= rgb.shape[0]:
                continue
            d = cell_diff(rgb, y, k, a, b) >= t
            if glyph_only:
                d &= rgb[y : y + 8 * k, a:b].max(axis=2) >= BRIGHT
            m[y : y + 8 * k, a:b] = d
    return m
