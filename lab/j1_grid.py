"""J1: cell-grid row finder (grid3) in front of the h4 fast union.
Fallback to the text-ladder finder when the grid gives < 2 team rows."""
import os

import numpy as np

import grid3
from common import parse
from h4_union import c5_on, d3_on
from h_common import g2_rows, vote
from rows import Row, Tab, find_tab, runs_of
from textmask import Shadow

PAD_L = int(os.environ.get("J_PADL", 10))
MODE = os.environ.get("J_MODE", "grid")  # grid | old


def grid_tab(rgb: np.ndarray) -> Tab | None:
    g = grid3.find_grid(rgb)
    if g is None:
        return None
    k = g.k
    mask = Shadow(rgb).mask(k)
    lo = max(0, min(a for a, _ in g.cols) - PAD_L * k)
    hi = min(rgb.shape[1], max(b for _, b in g.cols) + 2 * k)
    rows = []
    for y in g.tops:
        band = mask[y : y + 8 * k, lo:hi]
        spans = [(lo + p, lo + q) for p, q in runs_of(band.any(axis=0))]
        if spans:
            rows.append(Row(y, spans[0][0], spans[-1][1], k, 0, spans))
    return Tab(k, rows, mask, len(rows)) if rows else None


def union(rgb, known, tab):
    tab, prows = parse(rgb, tab)
    if tab is None or not known:
        return {}, prows
    g = g2_rows(rgb, known, tab, prows)
    res = [{n: t for n, (t, _) in g.items()}, d3_on(rgb, tab, prows, known), c5_on(tab, prows, known)]
    return vote(res), prows


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    if MODE == "grid":
        tab = grid_tab(rgb)
        if tab is not None:
            out, prows = union(rgb, known, tab)
            if sum(1 for p in prows if p.team) >= 2:
                return out
    return union(rgb, known, find_tab(rgb))[0]
