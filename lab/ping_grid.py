"""Ping anchor: find tab rows from the ping icons (for Lunar, which draws no
row cells).

The ping icon is an opaque texture (10 x 8 GUI px) at the right end of each
row, so its pixels repeat exactly at the row pitch 9k. Text that is the same
in each row (scores, team letters) also repeats; panel pixels repeat only on a
flat world. So: E = pixel is bright and equal to the pixel 9k below. The ping
column is the rightmost x band where E holds in many rows.

Returns a grid3.Grid (k, cell tops, cell x-ranges), so the j2 adapter works.
"""
import os
import sys
import time
from collections import Counter

import cv2
import numpy as np

from grid3 import Grid, runs_of

BRIGHT = int(os.environ.get("P_BRIGHT", 96))
TOL = int(os.environ.get("P_TOL", 3))
EDGE = int(os.environ.get("P_EDGE", 40))


MIN_RATE = float(os.environ.get("P_RATE", 0.6))
MAX_GAP = float(os.environ.get("P_GAP", 0.3))
NCAND = int(os.environ.get("P_NCAND", 6))
DEBUG = os.environ.get("P_DEBUG") == "1"


def bright_mask(rgb):
    r, g, b = cv2.split(rgb)
    return cv2.compare(cv2.max(cv2.max(r, g), b), BRIGHT - 1, cv2.CMP_GT)


def masks(rgb, k, bright):
    """B: bright pixel with an edge k px to the side (flat world repeats at
    any pitch, icons do not). E: B and the same as the pixel 9k below.
    uint8 0 / 1."""
    p = 9 * k
    lo = EDGE - 1
    d = cv2.bitwise_not(cv2.inRange(cv2.absdiff(rgb[:, k:], rgb[:, :-k]), (0, 0, 0), (lo, lo, lo)))
    edge = np.zeros(rgb.shape[:2], np.uint8)
    edge[:, :-k] = d
    edge[:, k:] |= d
    B = cv2.bitwise_and(edge, bright) // 255
    same = cv2.inRange(cv2.absdiff(rgb[:-p], rgb[p:]), (0, 0, 0), (TOL, TOL, TOL)) // 255
    E = np.zeros_like(B)
    E[:-p] = B[:-p] & same
    return B, E


def candidates(E, k):
    """x centres of the NCAND strongest 10k-wide bands of repeating pixels"""
    col = E.sum(axis=0, dtype=np.int64).astype(np.float32)
    win = cv2.boxFilter(col[None], -1, (10 * k, 1), normalize=False, borderType=cv2.BORDER_CONSTANT)[0]
    out = []
    for x in np.argsort(-win):
        if win[x] < 2 * 10 * k or len(out) >= NCAND:
            break
        if all(abs(int(x) - o) >= 10 * k for o in out):
            out.append(int(x))
    return out


def phase(E, k, x0, x1):
    """row top (mod 9k) and drop ratio. Icons (bars and shadow) and text
    (glyph and shadow) both end at GUI row 7 of the row, so the largest
    drop in the residue profile is the row bottom. Ratio: gap / last row
    (1.0 for a vertical line)."""
    p = 9 * k
    r = E[:, x0:x1].sum(axis=1, dtype=np.int64)
    acc = np.bincount(np.arange(len(r)) % p, weights=r, minlength=p)
    g = np.max([np.roll(acc, -1 - i) for i in range(k)], axis=0)  # gap rows after s
    s = int(np.argmax(acc - 3 * g))
    gap = g[s]
    return (s + 1 - 8 * k) % p, gap / max(1.0, acc[s])


def band(rgb, B, E, k, xc):
    """rows of one ping column candidate; returns (tops, rate)"""
    H, W = B.shape
    p = 9 * k
    x0, x1 = max(0, xc - 5 * k), min(W, xc + 5 * k)
    t, gap = phase(E, k, x0, x1)
    if gap > MAX_GAP:  # a vertical line, not icons
        return [], 0.0, (x0, x1)
    b = B[:, x0:x1].sum(axis=1, dtype=np.int64)
    e = E[:, x0:x1].sum(axis=1, dtype=np.int64)
    ys, eb = [], []
    for y in range(t, H - 8 * k + 1, p):
        bs, es = b[y:y + 8 * k].sum(), e[y:y + 8 * k].sum()
        if bs < 3 * k * k:
            continue
        ok = es >= 0.6 * bs
        last = ys and ys[-1] == y - p and _same_icon(rgb, B, y - p, y, x0, x1)
        if ok or last:
            ys.append(y)
            eb.append((es, bs) if ok else (0, 0))
    tops = _longest_chain(ys, p)
    if len(tops) < 2:
        return [], 0.0, (x0, x1)
    es = sum(v[0] for y, v in zip(ys, eb) if tops[0] <= y <= tops[-1])
    bs = sum(b[y:y + 8 * k].sum() for y in tops)
    return tops, es / max(1, bs), (x0, x1)


def pixel_scale(rgb, tops, k, x0, x1):
    """GUI scale of the band content: the largest m such that >= 90 % of
    the horizontal runs of one bright colour have a length divisible by m"""
    lens = []
    for y in tops:
        blk = rgb[y:y + 8 * k, x0:x1].astype(np.int32)
        code = (blk[..., 0] << 16) | (blk[..., 1] << 8) | blk[..., 2]
        bright = blk.max(axis=2) >= BRIGHT
        for row, br in zip(code, bright):
            ch = np.flatnonzero(np.diff(row) != 0) + 1
            starts = np.concatenate([[0], ch])
            ends = np.concatenate([ch, [len(row)]])
            for a, b in zip(starts[1:-1], ends[1:-1]):  # skip runs cut by the band edge
                if br[a]:
                    lens.append(b - a)
    if len(lens) < 10:
        return 0
    lens = np.array(lens)
    for m in range(6, 0, -1):
        if (lens % m == 0).mean() >= 0.9:
            return m
    return 0


def head_x(rgb, tops, k, px0):
    """left edge of the head column. The head is the only thing that spans
    all 8k pixel rows of a row (glyphs leave GUI row 0 empty), so its left
    and right edges are full-height vertical edges in most rows."""
    lo = max(1, px0 - 250 * k)
    hits = np.zeros(px0 - lo, np.float32)
    for y in tops:
        blk = rgb[y:y + 8 * k, lo - 1:px0].astype(np.int16)
        d = np.abs(np.diff(blk, axis=1)).max(axis=2) >= 12
        hits += d.sum(axis=0) >= 8 * k - 1
    f = hits / len(tops)
    for i in range(len(f) - 8 * k):
        if f[i] >= 0.6 and f[i + 8 * k] >= 0.6:
            return lo + i
    i = np.flatnonzero(f >= 0.6)
    return lo + int(i[0]) if len(i) else None


def find_ping(rgb, ks=range(1, 7)):
    H, W = rgb.shape[:2]
    best = None
    bright = bright_mask(rgb)
    for k in ks:
        if 18 * k >= H:
            break
        B, E = masks(rgb, k, bright)
        for xc in candidates(E, k):
            tops, rate, cols = band(rgb, B, E, k, xc)
            if len(tops) < 2 or rate < MIN_RATE or (len(tops) == 2 and rate < 0.9):
                continue
            m = pixel_scale(rgb, tops, k, *cols)
            if DEBUG:
                print(f"  k {k} x {cols} rows {len(tops)} y0 {tops[0]} rate {rate:.2f} scale {m}")
            if m != k:
                continue
            sc = len(tops) * rate
            if best is None or sc > best.score:
                best = Grid(k, tops, [cols], sc)
    if best is not None:
        # cell x-range as grid3 gives it: head at x0, ping ends k before x1
        k, (px0, px1) = best.k, best.cols[0]
        hx = head_x(rgb, best.tops, k, px0)
        best.cols = [(hx if hx is not None else px0 - 150 * k, px1 + k)]
        best.weak = hx is None
    return best


def _same_icon(rgb, B, y0, y1, x0, x1):
    """the icon pixels (B in either row) are the same in both rows"""
    h = y1 - y0
    a = rgb[y0:y0 + h, x0:x1].astype(np.int16)
    b = rgb[y1:y1 + h, x0:x1].astype(np.int16)
    if a.shape != b.shape:
        return False
    br = (B[y0:y0 + h, x0:x1] | B[y1:y1 + h, x0:x1]) > 0
    if br.sum() == 0:
        return False
    return (np.abs(a - b).max(axis=2)[br] <= TOL).mean() >= 0.8


def _longest_chain(tops, p, miss=2):
    best, cur = [], []
    for y in tops:
        if cur and y - cur[-1] > p * (miss + 1):
            cur = []
        cur.append(y)
        if len(cur) > len(best):
            best = list(cur)
    return list(range(best[0], best[-1] + 1, p)) if best else []


if __name__ == "__main__":
    from data import image, label, train_names

    only = sys.argv[1] if len(sys.argv) > 1 else "lunar"
    c = Counter()
    ts = []
    for n in train_names():
        if only not in n:
            continue
        rgb = image(n)
        lab = label(n)
        want = len(lab["rows"]) + len(lab["npcs"])
        t = time.perf_counter()
        g = find_ping(rgb)
        ts.append(time.perf_counter() - t)
        got = len(g.tops) if g else 0
        ok = got == want
        c["n"] += 1
        c["ok"] += ok
        c["rows"] += want
        c["rows_ok"] += want if ok else 0
        print(f"{'OK ' if ok else 'BAD'} {n:68s} want {want:2d} got {got:2d} k {g.k if g else 0}"
              f" cols {g.cols if g else None} y0 {g.tops[0] if g else None}")
    ts.sort()
    print(sorted(c.items()), "ms median", round(1000 * ts[len(ts) // 2]), "max", round(1000 * ts[-1]))
