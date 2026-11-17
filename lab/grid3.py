"""Cell-grid detector v3: find tab rows from the row-cell backgrounds.

Vanilla draws each row cell as 0x20FFFFFF (8 GUI px high, pitch 9) on the
panel 0x80000000: cell = bg*0.4375 + 32, separator = bg*0.5. So there is an
up edge at the cell top and a down edge 8k below, on all channels, for any
font / palette. Lunar draws no cells (use another finder there).
"""
import os
import sys
import time
from collections import Counter
from dataclasses import dataclass

import cv2
import numpy as np

LO = int(os.environ.get("G_LO", 6))
HI = int(os.environ.get("G_HI", 60))
THR = int(os.environ.get("G_THR", 14))  # min pair px per row, in k
MISS = int(os.environ.get("G_MISS", 2))


@dataclass
class Grid:
    k: int
    tops: list[int]  # first pixel row of each cell
    cols: list[tuple[int, int]]  # x-range of each tab column
    score: float
    weak: bool = False


def runs_of(b):
    d = np.diff(np.concatenate([[0], b.astype(np.int8), [0]]))
    return list(zip(np.flatnonzero(d == 1).tolist(), np.flatnonzero(d == -1).tolist()))


def edges(rgb, lo, hi):
    """U[y]: row y is lo..hi brighter than y-1 (all channels); D[y]: darker."""
    a, b = rgb[:-1], rgb[1:]
    lo3, hi3 = (lo, lo, lo), (hi, hi, hi)
    H, W = rgb.shape[:2]
    D = np.zeros((H, W), np.uint8)
    U = np.zeros((H, W), np.uint8)
    D[1:] = cv2.inRange(cv2.subtract(a, b), lo3, hi3)
    U[1:] = cv2.inRange(cv2.subtract(b, a), lo3, hi3)
    return U, D


def _find(rgb, ks, lo, hi):
    U, D = edges(rgb, lo, hi)
    H, W = U.shape
    best = None
    for k in ks:
        P = cv2.bitwise_and(U[: H - 8 * k], D[8 * k :])
        cnt = cv2.reduce(P, 1, cv2.REDUCE_SUM, dtype=cv2.CV_32S)[:, 0] // 255
        ys = np.flatnonzero(cnt >= THR * k)
        if len(ys) == 0:
            continue
        yset = set(ys.tolist())
        used = set()
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
            sup = cv2.morphologyEx(sup.astype(np.uint8)[None], cv2.MORPH_CLOSE, np.ones((1, 8 * k + 1), np.uint8))[0] > 0
            cols = [(a, b) for a, b in runs_of(sup) if b - a >= 30 * k]
            if not cols:
                continue
            width = sum(b - a for a, b in cols)
            sc = len(chain) * width / k
            if best is None or sc > best.score:
                tops = list(range(chain[0], chain[-1] + 1, 9 * k))
                best = Grid(k, tops, cols, sc)
    return best


def refine_cols(rgb, g):
    """Exact cell x-ranges: columns where the first / last cell pixel row
    differs from the separator row next to it, in most rows. Left of the
    cell both are panel background. Real tab columns are 5k apart."""
    k = g.k
    H = rgb.shape[0]
    t = np.array([y for y in g.tops if y >= 1 and y + 8 * k < H])
    if len(t) == 0:
        return g.cols
    a = np.abs(rgb[t].astype(np.int16) - rgb[t - 1].astype(np.int16)).max(axis=2) >= 8
    b = np.abs(rgb[t + 8 * k - 1].astype(np.int16) - rgb[t + 8 * k].astype(np.int16)).max(axis=2) >= 8
    f = (a | b).mean(axis=0) >= 0.5
    f = cv2.morphologyEx(f.astype(np.uint8)[None], cv2.MORPH_CLOSE, np.ones((1, 3 * k + 1), np.uint8))[0] > 0
    lo, hi = min(c[0] for c in g.cols), max(c[1] for c in g.cols)
    cols = [(p, q) for p, q in runs_of(f) if q - p >= 30 * k and q > lo and p < hi]
    return cols or g.cols


def find_grid(rgb, ks=range(1, 7)):
    g = _find_any(rgb, ks)
    if g is not None:
        g.cols = refine_cols(rgb, g)
    return g


def _find_any(rgb, ks=range(1, 7)):
    g = _find(rgb, ks, LO, HI)
    if g is None or len(g.tops) < 3:
        w = _find(rgb, ks, 2, 9)  # under a translucent overlay
        if w is not None and (g is None or len(w.tops) > len(g.tops)):
            w.weak = True
            return w
    return g


if __name__ == "__main__":
    from data import image, label, train_names

    only = sys.argv[1] if len(sys.argv) > 1 else ""
    c = Counter()
    ts = []
    for n in train_names():
        if only not in n:
            continue
        rgb = image(n)
        lab = label(n)
        want = len(lab["rows"]) + len(lab["npcs"])
        t = time.perf_counter()
        g = find_grid(rgb)
        ts.append(time.perf_counter() - t)
        got = len(g.tops) if g else 0
        gs = lab["setup"]["gui_scale"]
        ncol = len(g.cols) if g else 0
        ok = (got * ncol >= want and got * (ncol - 1) < want) if ncol > 1 else got == want
        grp = "lunar" if "lunar" in n else "notab" if want == 0 else "cells"
        c[grp] += 1
        c[grp + "_ok"] += ok
        c[grp + "_rows"] += want
        c[grp + "_rows_ok"] += want if ok else 0
        if not ok or (g and g.k != gs) or only:
            print(f"{'OK ' if ok else 'BAD'} {n:68s} want {want:2d} got {got:2d} gs {gs} k {g.k if g else 0} weak {g.weak if g else None}"
                  f" cols {g.cols if g else None} y0 {g.tops[0] if g else None} ov {lab.get('overlay')}")
    ts.sort()
    print(sorted(c.items()), "ms median", round(1000 * ts[len(ts) // 2]), "max", round(1000 * ts[-1]))
