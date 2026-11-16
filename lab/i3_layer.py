"""I3 layer stage: h5_layer OCR lines with their y. A line with no team
letter before the name is still accepted when its colour layer equals the
team of the found rows above and below it (teams are sorted, contiguous
blocks in the tab on all train images)."""

import numpy as np

import h5_layer as hl
from common import assign, parse

ALLOW_WHITE = True


def lines_y(rgb, known):
    """h5_layer.layer_lines, but (texts, team, y)"""
    bs = hl.rb.bands(rgb)
    if not bs:
        return []
    k = bs[0][3]
    sh = hl.Shadow(rgb).mask(k)
    h, w, _ = rgb.shape
    out, seen = [], set()
    for y, x0, x1, k in bs:
        y0, y1 = max(0, y - k), min(h - k, y + 9 * k)
        x0 = max(0, x0 - hl.WIDEN * k)
        x1 = min(w - k, x1 + hl.WIDEN // 4 * k)
        sub = sh[y0:y1:k, x0:x1:k]
        ys, xs = np.nonzero(sub)
        if len(ys) < 12:
            continue
        iy, ix = y0 + ys * k, x0 + xs * k
        t = hl.hue(rgb[iy, ix])
        s = hl.hue(rgb[iy + k, ix + k], 4)
        t = np.where(t >= 0, t, s)
        for ti in np.unique(t):
            if ti < 0 or (t == ti).sum() < 12:
                continue
            m = np.zeros(sub.shape, bool)
            m[ys[t == ti], xs[t == ti]] = True
            m = hl.fill(rgb[y0:y1:k, x0:x1:k], m)
            for a, b in hl.segments(m):
                seg = m[:, a:b]
                key = (ti, y, seg.tobytes(), seg.shape)
                if seg.sum() < 12 or key in seen:
                    continue
                seen.add(key)
                txts = []
                for sc in hl.SCALES:
                    txt = hl.rec(hl.render(seg, sc))
                    if txt.strip():
                        txts.append(txt)
                    if hl.best(txts, known, hl.TEAMS[ti]) >= hl.GOOD:
                        break
                if txts:
                    out.append((tuple(txts), hl.TEAMS[ti], y, k))
    return out


def loose(name, txts, team):
    hl.NEED_PRE, hl.STRICT = False, False
    try:
        return max(hl.score(name, t, team) for t in txts)
    finally:
        hl.NEED_PRE, hl.STRICT = True, True


def block_team(prows, y, k):
    """team of the nearest letter rows above and below y, if they agree"""
    tr = sorted((p.row.y, p.team) for p in prows if p.team)
    up = [t for yy, t in tr if yy < y - 4 * k]
    dn = [t for yy, t in tr if yy > y + 4 * k]
    if up and dn and up[-1] == dn[0]:
        return up[-1]
    return None


def stage(rgb, known, out, prows=None):
    out = dict(out)
    left = [n for n in known if n not in out]
    if not left:
        return out
    if prows is None:
        _, prows = parse(rgb)
    if not prows:
        return out
    lines = list(dict.fromkeys(lines_y(rgb, left)))
    if not lines:
        return out
    cost = np.ones((len(lines), len(left)))
    for i, (ts, tm, y, k) in enumerate(lines):
        bt = block_team(prows, y, k)
        ok = bt == tm and (ALLOW_WHITE or tm != "white")
        for j, n in enumerate(left):
            s = hl.best(list(ts), [n], tm)
            if s == 0 and ok:
                s = loose(n, ts, tm)
            cost[i, j] = 1 - s
    for i, j in assign(cost, hl.MAX_COST, hl.MARGIN):
        out[left[j]] = lines[i][1]
    return out
