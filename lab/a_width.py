"""A: name word pixel width vs vanilla width of each known name."""

import numpy as np

import font
from common import assign, parse


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    tab, prows = parse(rgb)
    if tab is None or not known:
        return {}
    k = tab.k
    cand = [p for p in prows if p.name is not None]
    widths = np.array([font.width(n) for n in known], float)
    cost = np.array([[abs((p.name.x1 - p.name.x0) / k - w) for w in widths] for p in cand])
    out = {}
    for i, j in assign(cost, max_cost=1.5, margin=2.0):
        if cand[i].team:
            out[known[j]] = cand[i].team
    return out
