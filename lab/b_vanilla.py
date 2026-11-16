"""B: render names in the vanilla font; IoU against the name word mask."""

import numpy as np

import font
from common import assign, parse


def iou(word_mask: np.ndarray, tmpl: np.ndarray, k: int) -> float:
    h = min(word_mask.shape[0], tmpl.shape[0])
    best = 0.0
    for dy in range(0, k + 1, max(1, k)):  # allow 1 font px vertical offset
        a = word_mask[dy : dy + h - dy]
        t = tmpl[: a.shape[0]]
        w = max(a.shape[1], t.shape[1])
        A = np.zeros((a.shape[0], w), bool)
        T = np.zeros((a.shape[0], w), bool)
        A[:, : a.shape[1]] = a
        T[:, : t.shape[1]] = t
        u = (A | T).sum()
        best = max(best, (A & T).sum() / u if u else 0.0)
    return best


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    tab, prows = parse(rgb)
    if tab is None or not known:
        return {}
    k = tab.k
    cand = [p for p in prows if p.name is not None]
    tmpls = [font.render(n, k) for n in known]
    cost = np.array([[1 - iou(p.name.mask, t, k) for t in tmpls] for p in cand])
    out = {}
    for i, j in assign(cost, max_cost=0.5, margin=0.1):
        if cand[i].team:
            out[known[j]] = cand[i].team
    return out
