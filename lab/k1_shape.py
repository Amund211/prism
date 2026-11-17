"""Idea 2 POC: word-shape code. Each glyph -> vertical class only:
T tall (capital, digit, ascender), x x-height, g descender, J tall +
descender, u underscore. Match the code of a row against the codes of the
known names (edit distance), Hungarian + margin. No font knowledge.

k1_shape.py uniq     how unique are the codes in the train `known` lists
(as a module)        read_teams for mybench; K_MASK bg | shadow
"""
import os
import sys
from collections import Counter

import numpy as np

TALL = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789bdfhiklt")
DESC = set("gpqy")
MASK = os.environ.get("K_MASK", "bg")
MAX_COST = float(os.environ.get("K_MAX", 0.34))
MARGIN = float(os.environ.get("K_MARGIN", 0.15))
MIN_LEN = int(os.environ.get("K_MINLEN", 4))


def code_of(name: str) -> str:
    out = []
    for c in name:
        if c == "_":
            out.append("u")
        elif c == "j":
            out.append("J")
        elif c in DESC:
            out.append("g")
        elif c in TALL:
            out.append("T")
        else:
            out.append("x")
    return "".join(out)


def runs_of(b):
    d = np.diff(np.concatenate([[0], b.astype(np.int8), [0]]))
    return list(zip(np.flatnonzero(d == 1).tolist(), np.flatnonzero(d == -1).tolist()))


def glyph_boxes(m: np.ndarray) -> list[tuple[int, int, int, int]]:
    """(x0, x1, top, bottom) per column run of the mask"""
    out = []
    for a, b in runs_of(m.any(axis=0)):
        ys = np.flatnonzero(m[:, a:b].any(axis=1))
        out.append((a, b, int(ys[0]), int(ys[-1]) + 1))
    return out


def classify(rows_boxes: list[list[tuple[int, int, int, int]]], k: int) -> list[str]:
    """Per image: cap top and baseline from all glyphs, then a code per row"""
    tops = np.array([b[2] for bx in rows_boxes for b in bx])
    bots = np.array([b[3] for bx in rows_boxes for b in bx])
    if len(tops) < 8:
        return ["" for _ in rows_boxes]
    cap = np.percentile(tops, 10)
    vals, cnt = np.unique(bots, return_counts=True)
    base = vals[cnt.argmax()]  # most glyphs end on the baseline
    # x-height top: the most common top that is clearly below the cap top
    low = tops[tops >= cap + 1.2 * k]
    xtop = np.median(low) if len(low) >= 3 else cap + 2 * k
    cut = (cap + xtop) / 2
    codes = []
    for bx in rows_boxes:
        s = []
        for _, _, t, b in bx:
            desc = b >= base + 0.6 * k
            if t >= base - 1.3 * k:
                s.append("u")
            elif t <= cut:
                s.append("J" if desc else "T")
            else:
                s.append("g" if desc else "x")
        codes.append("".join(s))
    return codes


def uniq():
    from data import label, train_names
    from rapidfuzz.distance import Levenshtein

    c = Counter()
    for n in train_names():
        lab = label(n)
        known = list(lab["known"])
        codes = {x: code_of(x) for x in known}
        for r in lab["rows"]:
            x = r["name"]
            if x not in codes:
                continue
            c["rows"] += 1
            others = [codes[o] for o in known if o != x]
            d = min((Levenshtein.distance(codes[x], o) for o in others), default=99)
            c["unique"] += d >= 1
            c["unique_d2"] += d >= 2
            c["unique_d3"] += d >= 3
    r = c["rows"]
    print(f"rows {r}: code unique {100 * c['unique'] / r:.1f} %, distance >= 2: {100 * c['unique_d2'] / r:.1f} %,"
          f" >= 3: {100 * c['unique_d3'] / r:.1f} %")


def shape_rows(rgb):
    """(tab, prows with a team and a name, code per prow)"""
    import grid3
    from bgmask import bg_mask
    from common import parse
    from j2_bg import grid_tab

    tab, _ = grid_tab(rgb)  # shadow seed (J_MASK is set by the runner)
    if tab is None:
        return None, [], []
    tab, prows = parse(rgb, tab)
    k = tab.k
    if MASK == "bg":
        g = grid3.find_grid(rgb)
        bm = bg_mask(rgb, g)
    else:
        bm = tab.mask
    prows = [p for p in prows if p.name is not None]
    boxes = [glyph_boxes(bm[p.row.y : p.row.y + 8 * k, p.name.x0 : p.name.x1]) for p in prows]
    return tab, prows, classify(boxes, k)


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    from common import assign
    from rapidfuzz.distance import Levenshtein
    from rapidfuzz.process import cdist

    tab, prows, codes = shape_rows(rgb)
    if tab is None or not prows or not known:
        return {}
    names = sorted(set(known))
    C = np.asarray(cdist(codes, [code_of(n) for n in names], scorer=Levenshtein.normalized_distance), float)
    for i, c in enumerate(codes):
        if len(c) < MIN_LEN:
            C[i] = 1.0
    out = {}
    for i, j in assign(C, MAX_COST, MARGIN):
        if prows[i].team:
            out[names[j]] = prows[i].team
    return out


if __name__ == "__main__":
    uniq()
