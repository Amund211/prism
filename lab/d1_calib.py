"""D1: font from header / footer text (known strings), vanilla for the rest."""

import numpy as np

from common import assign
from d_core import Font, cost_matrix, extract

MAX_COST = 0.40  # tuned on train (d_tune.py)
MARGIN = 0.1


def build(rgb: np.ndarray):
    ext = extract(rgb)
    f = Font()
    if ext:
        for c, g in ext.calib:
            f.add(c, g)
    return ext, f


def finish(ext, names, C, max_cost=MAX_COST, margin=MARGIN) -> dict[str, str]:
    out = {}
    for i, j in assign(C, max_cost, margin):
        if ext.rows[i].team:
            out[names[j]] = ext.rows[i].team
    return out


def costs(rgb: np.ndarray, known: list[str]):
    names = sorted(set(known))
    ext, f = build(rgb)
    if not ext or not ext.rows or not names:
        return [], names, None
    C, _ = cost_matrix(ext, names, f)
    return [r.team for r in ext.rows], names, C


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    names = sorted(set(known))
    ext, f = build(rgb)
    if not ext or not ext.rows or not names:
        return {}
    C, _ = cost_matrix(ext, names, f)
    return finish(ext, names, C)
