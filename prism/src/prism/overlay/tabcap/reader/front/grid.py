"""Cell-grid detector v3: find tab rows from the row-cell backgrounds.

Vanilla draws each row cell as 0x20FFFFFF (8 GUI px high, pitch 9) on the
panel 0x80000000: cell = bg*0.4375 + 32, separator = bg*0.5. So there is an
up edge at the cell top and a down edge 8k below, on all channels, for any
font / palette. Lunar draws no cells (use another finder there).
"""

from dataclasses import dataclass

import cv2
import numpy as np

from prism.overlay.tabcap.reader.front.guiscale import Array, gui_ks
from prism.overlay.tabcap.reader.front.rows import runs_of

LO = 6
HI = 60
THR = 14  # min pair px per row, in k
MISS = 2


@dataclass
class Grid:
    k: int
    tops: list[int]  # first pixel row of each cell
    cols: list[tuple[int, int]]  # x-range of each tab column
    score: float
    weak: bool = False


def edges(rgb: Array, lo: int, hi: int) -> tuple[Array, Array]:
    """U[y]: row y is lo..hi brighter than y-1 (all channels); D[y]: darker."""
    a, b = rgb[:-1], rgb[1:]
    lo3, hi3 = (lo, lo, lo), (hi, hi, hi)
    H, W = rgb.shape[:2]
    D = np.zeros((H, W), np.uint8)
    U = np.zeros((H, W), np.uint8)
    D[1:] = cv2.inRange(cv2.subtract(a, b), lo3, hi3)
    U[1:] = cv2.inRange(cv2.subtract(b, a), lo3, hi3)
    return U, D


def _find(rgb: Array, ks: range, lo: int, hi: int) -> Grid | None:
    U, D = edges(rgb, lo, hi)
    H, W = U.shape
    best: Grid | None = None
    for k in ks:
        P = cv2.bitwise_and(U[: H - 8 * k], D[8 * k :])
        cnt = cv2.reduce(P, 1, cv2.REDUCE_SUM, dtype=cv2.CV_32S)[:, 0] // 255
        ys = np.flatnonzero(cnt >= THR * k)
        if len(ys) == 0:
            continue
        yset = set(ys.tolist())
        used: set[int] = set()
        for y in ys.tolist():
            if y in used:
                continue
            chain = [y]
            miss = 0
            yy = y
            while miss <= MISS:
                yy += 9 * k
                if yy in yset:
                    chain.append(yy)
                    miss = 0
                else:
                    miss += 1
            used.update(chain)
            if len(chain) < 2:
                continue
            sup = (P[chain] > 0).mean(axis=0) >= 0.4
            sup = (
                cv2.morphologyEx(
                    sup.astype(np.uint8)[None],
                    cv2.MORPH_CLOSE,
                    np.ones((1, 8 * k + 1), np.uint8),
                )[0]
                > 0
            )
            cols = [(a, b) for a, b in runs_of(sup) if b - a >= 30 * k]
            if not cols:
                continue
            width = sum(b - a for a, b in cols)
            sc = len(chain) * width / k
            if best is None or sc > best.score:
                tops = list(range(chain[0], chain[-1] + 1, 9 * k))
                best = Grid(k, tops, cols, sc)
    return best


def refine_cols(rgb: Array, g: Grid) -> list[tuple[int, int]]:
    """Exact cell x-ranges: columns where the first / last cell pixel row
    differs from the separator row next to it, in most rows. Left of the
    cell both are panel background. Real tab columns are 5k apart."""
    k = g.k
    H = rgb.shape[0]
    t = np.array([y for y in g.tops if y >= 1 and y + 8 * k < H])
    if len(t) == 0:
        return g.cols
    i16 = np.int16
    a = np.abs(rgb[t].astype(i16) - rgb[t - 1].astype(i16)).max(axis=2) >= 8
    b = (
        np.abs(rgb[t + 8 * k - 1].astype(i16) - rgb[t + 8 * k].astype(i16)).max(axis=2)
        >= 8
    )
    f = (a | b).mean(axis=0) >= 0.5
    f = (
        cv2.morphologyEx(
            f.astype(np.uint8)[None],
            cv2.MORPH_CLOSE,
            np.ones((1, 3 * k + 1), np.uint8),
        )[0]
        > 0
    )
    lo, hi = min(c[0] for c in g.cols), max(c[1] for c in g.cols)
    cols = [(p, q) for p, q in runs_of(f) if q - p >= 30 * k and q > lo and p < hi]
    return cols or g.cols


def find_grid(rgb: Array, ks: range | None = None) -> Grid | None:
    g = _find_any(rgb, ks)
    if g is not None:
        g.cols = refine_cols(rgb, g)
    return g


def _find_any(rgb: Array, ks: range | None = None) -> Grid | None:
    ks = gui_ks(rgb) if ks is None else ks
    g = _find(rgb, ks, LO, HI)
    if g is None or len(g.tops) < 3:
        w = _find(rgb, ks, 2, 9)  # under a translucent overlay
        if w is not None and (g is None or len(w.tops) > len(g.tops)):
            w.weak = True
            return w
    return g
