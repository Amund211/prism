"""Find tab-list rows: ladders of text lines with pitch 9k at GUI scale k."""

from dataclasses import dataclass, field

import cv2
import numpy as np

from prism.overlay.tabcap.reader.front.guiscale import Array, gui_ks
from prism.overlay.tabcap.reader.front.textmask import Shadow


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
    mask: Array  # shadow mask at k (full image)
    real: int = 0


@dataclass
class Chain:
    tops: list[int]
    lo: int
    hi: int
    real: int
    bx: Array | None = None  # the chain's boxes


def _comps(mask: Array, k: int) -> Array:
    """Word boxes [x, y, w, h]. Vertical closing < k: fills thin-stroke
    breaks (HD fonts) but not the >= k gap between rows."""
    m = mask.astype(np.uint8)
    out = []
    for kh in (1, k) if k > 2 else (1,):
        c = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((kh, 3 * k + 1), np.uint8))
        _, _, stats, _ = cv2.connectedComponentsWithStats(c, connectivity=8)
        out.append(stats[1:, :4])
    return np.unique(np.concatenate(out), axis=0)


def runs_of(cols: Array) -> list[tuple[int, int]]:
    d = np.diff(np.concatenate([[0], cols.astype(np.int8), [0]]))
    return list(zip(np.flatnonzero(d == 1).tolist(), np.flatnonzero(d == -1).tolist()))


def _ladders(boxes: Array, k: int, min_h: int = 6) -> list[Chain]:
    """Chains of full-height boxes, top-to-top 9k (or 18k: one row missing)"""
    pitch = 9 * k
    tol = max(1, k // 2)
    full = boxes[(boxes[:, 3] >= min_h * k) & (boxes[:, 3] <= 8 * k + 1)]
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
        chains.append(Chain(tops, lo, hi, real, full[chain]))
    return chains


def _right_edge(c: Chain, k: int) -> int | None:
    """Common right edge of a right-aligned chain (>= 70 % of its boxes)"""
    if c.real < 3 or c.bx is None:
        return None
    x1 = c.bx[:, 0] + c.bx[:, 2]
    med = int(np.median(x1))
    return med if (np.abs(x1 - med) <= k).mean() >= 0.7 else None


def _columns(chains: list[Chain], lo: int, hi: int, k: int) -> list[tuple[int, int]]:
    """Two-column tab lists: two equal columns, each ending with the right-
    aligned score and then the ping icon (~12k). Cut after a right-aligned
    chain whose column end is near the panel middle."""
    mid = (lo + hi) // 2
    cuts = []
    for c in chains:
        e = _right_edge(c, k) if c.lo >= lo and c.hi <= hi else None
        if e is not None and abs(e + 12 * k - mid) <= 8 * k:
            cuts.append(e + 12 * k)
    if cuts and hi - lo >= 120 * k:
        cut = max(cuts) + 1
        return [(lo, cut), (cut, hi)]
    return [(lo, hi)]


def _in_rows(boxes: Array, tops: list[int], k: int) -> Array:
    """Boxes that sit in one of the row bands"""
    t = np.array(tops)
    d = boxes[:, 1][:, None] - t[None, :]
    ok = (np.abs(d) <= 2 * k + 1) & (
        boxes[:, 1][:, None] + boxes[:, 3][:, None] <= t[None, :] + 8 * k + 1
    )
    out: Array = boxes[ok.any(axis=1)]
    return out


def _grow(boxes: Array, lo: int, hi: int, gap: int) -> tuple[int, int]:
    """Grow [lo, hi) by boxes at most gap away, until stable (panel x-range)"""
    if len(boxes) == 0:
        return lo, hi
    x0 = boxes[:, 0]
    x1 = boxes[:, 0] + boxes[:, 2]
    while True:
        near = (x1 > lo - gap) & (x0 < hi + gap)
        nlo = min(lo, int(x0[near].min())) if near.any() else lo
        nhi = max(hi, int(x1[near].max())) if near.any() else hi
        if (nlo, nhi) == (lo, hi):
            return lo, hi
        lo, hi = nlo, nhi


def _band(boxes: Array, lo: int, hi: int, y: int, k: int) -> Array:
    sel = (np.abs(boxes[:, 1] - y) <= 2 * k + 1) & (
        boxes[:, 1] + boxes[:, 3] <= y + 8 * k + 1
    )
    sel &= (boxes[:, 0] + boxes[:, 2] > lo) & (boxes[:, 0] < hi)
    return boxes[sel]


def _extent(
    boxes: Array,
    ch: Chain,
    k: int,
    chains: list[Chain] | None = None,
    core: list[int] | None = None,
) -> tuple[int, int]:
    """Panel x-range: union of the chains on the same rows (letter, name,
    score columns), then boxes in the rows that touch it"""
    lo, hi = ch.lo, ch.hi
    tol = max(1, k // 2)
    t = np.array(ch.tops)
    same_rows = [
        c
        for c in chains or []
        if c is not ch
        and c.real >= 3
        and sum(1 for y in c.tops if np.abs(t - y).min() <= tol)
        >= max(3, (c.real + 1) // 2)
    ]
    changed = True
    while changed:
        changed = False
        for c in same_rows:
            if c.hi > lo - 40 * k and c.lo < hi + 40 * k and (c.lo < lo or c.hi > hi):
                lo, hi = min(lo, c.lo), max(hi, c.hi)
                changed = True
    if core is not None:
        core[:] = [lo, hi]
    return _grow(_in_rows(boxes, ch.tops, k), lo, hi, 2 * k)


def find_rows_k(mask: Array, k: int, min_h: int = 6) -> tuple[list[Row], int]:
    boxes = _comps(mask, k)
    chains = sorted(_ladders(boxes, k, min_h), key=lambda c: -c.real)
    if not chains or chains[0].real < 2:
        return [], 0
    a = chains[0]
    core = [0, 0]  # chain-union x-range, without header / footer growth
    ext = _extent(boxes, a, k, chains, core)
    # row tops: the main chain plus chains in the panel on the same pitch
    # (a second column can be longer or shorter than the first)
    pitch, tol = 9 * k, max(1, k // 2)
    tops = list(a.tops)
    for c in chains[1:]:
        if c.lo >= ext[0] and c.hi <= ext[1] and c.real >= 2:
            for y in c.tops:
                d = (y - a.tops[0]) % pitch
                if min(d, pitch - d) <= tol and all(abs(y - t) > tol for t in tops):
                    tops.append(y)
    tops.sort()
    rows = []
    cols = _columns(chains, core[0], core[1], k)
    cols[0] = (ext[0], cols[0][1])
    cols[-1] = (cols[-1][0], ext[1])
    for col, (lo, hi) in enumerate(cols):
        for y in tops:
            inband = _band(boxes, lo, hi, y, k)
            if len(inband) == 0:
                continue
            x0 = max(lo, int(inband[:, 0].min()))
            x1 = min(hi, int((inband[:, 0] + inband[:, 2]).max()))
            band = mask[y : y + 8 * k, x0:x1]
            spans = [(x0 + p, x0 + q) for p, q in runs_of(band.any(axis=0))]
            rows.append(Row(y, x0, x1, k, col, spans))
    return rows, a.real


def find_tab(rgb: Array, ks: range | None = None) -> Tab | None:
    # Text at scale s also passes the shadow test at k < s, and its parts can
    # form a false ladder there. So take the largest k with a good ladder.
    sh = Shadow(rgb)
    ks = gui_ks(rgb) if ks is None else ks
    masks = {k: sh.mask(k) for k in ks}
    best = _pick(masks, ks, min_h=6)
    if best is None or best.real < 5:
        # anti-aliased fonts: few glyphs pass the shadow test over 6k
        low = _pick(masks, ks, min_h=5)
        if low is not None and (best is None or low.real > best.real):
            best = low
    return best


def _pick(masks: dict[int, Array], ks: range, min_h: int) -> Tab | None:
    tabs = []
    for k in ks:
        rows, real = find_rows_k(masks[k], k, min_h)
        if real >= 2:
            tabs.append(Tab(k, rows, masks[k], real))
    if not tabs:
        return None
    top = max(t.real for t in tabs)
    # (a 2-3 row ladder of junk at a large k must not win over the tab)
    ok = [
        t for t in tabs if t.real >= max(2, top // 2) and (t.real >= 4 or t.real == top)
    ]
    return max(ok, key=lambda t: t.k)
