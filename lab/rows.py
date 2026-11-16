"""Find tab-list rows: ladders of text lines with pitch 9k at GUI scale k."""

from dataclasses import dataclass, field

import cv2
import numpy as np

from textmask import shadow_mask


@dataclass
class Row:
    y: int  # top of the glyph area
    x0: int
    x1: int
    k: int
    col: int = 0  # tab column (two-column lists)
    runs: list[tuple[int, int]] = field(default_factory=list)  # glyph column spans


@dataclass
class Tab:
    k: int
    rows: list[Row]
    mask: np.ndarray  # shadow mask at k (full image)
    real: int = 0


@dataclass
class Chain:
    tops: list[int]
    lo: int
    hi: int
    real: int


def _comps(mask: np.ndarray, k: int) -> np.ndarray:
    """Word boxes [x, y, w, h] (horizontal closing only, so rows stay apart)"""
    m = mask.astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((1, 3 * k + 1), np.uint8))
    _, _, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    return stats[1:, :4]


def runs_of(cols: np.ndarray) -> list[tuple[int, int]]:
    d = np.diff(np.concatenate([[0], cols.astype(np.int8), [0]]))
    return list(zip(np.flatnonzero(d == 1).tolist(), np.flatnonzero(d == -1).tolist()))


def _ladders(boxes: np.ndarray, k: int) -> list[Chain]:
    """Chains of full-height boxes, top-to-top 9k (or 18k: one row missing)"""
    pitch = 9 * k
    tol = max(1, k // 2)
    full = boxes[(boxes[:, 3] >= 6 * k) & (boxes[:, 3] <= 8 * k + 1)]
    full = full[np.argsort(full[:, 1], kind="stable")]
    used = np.zeros(len(full), bool)
    chains = []
    for i in range(len(full)):
        if used[i]:
            continue
        chain = [i]
        y = int(full[i, 1])
        lo, hi = int(full[i, 0]), int(full[i, 0] + full[i, 2])
        tops = [y]
        real = 1
        while True:
            dy = full[:, 1] - y
            near = (full[:, 0] < hi) & (full[:, 0] + full[:, 2] > lo)
            cand = np.flatnonzero((np.abs(dy - pitch) <= tol) & near)
            step = 1
            if len(cand) == 0:
                cand = np.flatnonzero((np.abs(dy - 2 * pitch) <= tol) & near)
                step = 2
            if len(cand) == 0:
                break
            same = cand[np.abs(full[cand, 1] - full[cand[0], 1]) <= tol]
            chain.extend(same.tolist())
            ny = int(full[cand[0], 1])
            if step == 2:
                tops.append(y + pitch)
            tops.append(ny)
            real += 1
            y = ny
            lo = min(lo, int(full[same, 0].min()))
            hi = max(hi, int((full[same, 0] + full[same, 2]).max()))
        used[chain] = True
        chains.append(Chain(tops, lo, hi, real))
    return chains


def _band(boxes: np.ndarray, ch: Chain, y: int, k: int) -> np.ndarray:
    sel = (np.abs(boxes[:, 1] - y) <= 2 * k + 1) & (boxes[:, 1] + boxes[:, 3] <= y + 8 * k + 1)
    sel &= (boxes[:, 0] + boxes[:, 2] > ch.lo - 60 * k) & (boxes[:, 0] < ch.hi + 60 * k)
    return boxes[sel]


def _extent(boxes: np.ndarray, ch: Chain, k: int) -> tuple[int, int]:
    xs = [b for y in ch.tops for b in _band(boxes, ch, y, k)]
    if not xs:
        return ch.lo, ch.hi
    arr = np.array(xs)
    return int(arr[:, 0].min()), int((arr[:, 0] + arr[:, 2]).max())


def find_rows_k(mask: np.ndarray, k: int) -> tuple[list[Row], int]:
    boxes = _comps(mask, k)
    chains = sorted(_ladders(boxes, k), key=lambda c: -c.real)
    if not chains or chains[0].real < 2:
        return [], 0
    picked = [chains[0]]
    a = chains[0]
    ext = _extent(boxes, a, k)
    for c in chains[1:]:
        # a second tab column: same rows, beside the first (not inside its rows)
        if (
            c.real >= max(3, a.real // 3)
            and (c.lo > ext[1] or c.hi < ext[0])
            and abs(c.tops[0] - a.tops[0]) % (9 * k) <= max(1, k // 2)
            and min(abs(c.lo - a.hi), abs(a.lo - c.hi)) < 120 * k
        ):
            picked.append(c)
            break
    picked.sort(key=lambda c: c.lo)
    rows = []
    real = 0
    for col, ch in enumerate(picked):
        real += ch.real
        for y in ch.tops:
            inband = _band(boxes, ch, y, k)
            if len(inband) == 0:
                continue
            x0 = int(inband[:, 0].min())
            x1 = int((inband[:, 0] + inband[:, 2]).max())
            band = mask[y : y + 8 * k, x0:x1]
            spans = [(x0 + a, x0 + b) for a, b in runs_of(band.any(axis=0))]
            rows.append(Row(y, x0, x1, k, col, spans))
    return rows, real


def find_tab(rgb: np.ndarray, ks: range = range(1, 7)) -> Tab | None:
    # Text at scale s also passes the shadow test at k < s, and its parts can
    # form a false ladder there. So take the largest k with a good ladder.
    tabs = []
    for k in ks:
        mask = shadow_mask(rgb, k)
        rows, real = find_rows_k(mask, k)
        if real >= 2:
            tabs.append(Tab(k, rows, mask, real))
    if not tabs:
        return None
    top = max(t.real for t in tabs)
    return max((t for t in tabs if t.real >= max(2, top // 2)), key=lambda t: t.k)
