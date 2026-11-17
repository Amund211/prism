"""J2: cell grid rows (exact cell range, all columns) + choice of text mask,
then the h4 matchers (g2 + d3 + c5 vote).

J_MASK  shadow | bg | union   seed mask given to common.parse
J_WMASK 1: the name word mask (and glyph spans) = bg mask in the word range
J_FALLBACK 1: use the old finder when the grid gives < 2 team rows
"""
import os

import numpy as np

import grid3
from bgmask import bg_mask
from common import parse
from h4_union import c5_on, d3_on
from h_common import g2_rows, vote
from rows import Row, Tab, find_tab, runs_of
from textmask import Shadow

MASK = os.environ.get("J_MASK", "bg")
WMASK = os.environ.get("J_WMASK", "0") == "1"
FALLBACK = os.environ.get("J_FALLBACK", "1") == "1"


def grid_tab(rgb: np.ndarray):
    return tab_from_grid(rgb, grid3.find_grid(rgb))


def tab_from_grid(rgb: np.ndarray, g):
    if g is None:
        return None, None
    k = g.k
    bm = bg_mask(rgb, g) if MASK != "shadow" or WMASK else None
    if MASK == "shadow":
        mask = Shadow(rgb).mask(k)
    elif MASK == "bg":
        mask = bm
    else:
        mask = Shadow(rgb).mask(k) | bm
    rows = []
    for col, (x0, x1) in enumerate(g.cols):
        lo, hi = x0 + 9 * k, x1 - 11 * k
        for y in g.tops:
            band = mask[y : y + 8 * k, lo:hi]
            spans = [(lo + p, lo + q) for p, q in runs_of(band.any(axis=0))]
            if spans:
                rows.append(Row(y, spans[0][0], spans[-1][1], k, col, spans))
    return (Tab(k, rows, mask, len(rows)) if rows else None), bm


def union(rgb, known, tab, bm=None):
    tab, prows = parse(rgb, tab)
    if tab is None or not known:
        return {}, prows
    if bm is not None and WMASK:
        k = tab.k
        for p in prows:
            w = p.name
            if w is not None:
                w.mask = bm[p.row.y : p.row.y + 8 * k, w.x0 : w.x1]
                sp = runs_of(w.mask.any(axis=0))
                if sp:
                    w.spans = [(w.x0 + a, w.x0 + b) for a, b in sp]
    g = g2_rows(rgb, known, tab, prows)
    res = [{n: t for n, (t, _) in g.items()}, d3_on(rgb, tab, prows, known), c5_on(tab, prows, known)]
    return vote(res), prows


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    tab, bm = grid_tab(rgb)
    if tab is not None:
        out, prows = union(rgb, known, tab, bm)
        if not FALLBACK or sum(1 for p in prows if p.team) >= 2:
            return out
    return union(rgb, known, find_tab(rgb))[0] if FALLBACK else {}
