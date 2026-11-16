"""C4: C2 profile cost prunes, C1 run alignment only on the top-K names per
row (and top-K rows per name); final cost = mean of both."""

import numpy as np

import c1_runs
import c1v_q
import c2_profile
from c_feats import RowF, feats

TOPK = 3
ACCEPT = (0.35, 0.06)


def costs(rows: list[RowF], known: list[str]) -> np.ndarray:
    c2 = c2_profile.costs(rows, known)
    keep = np.zeros_like(c2, bool)
    kr = min(TOPK, c2.shape[1])
    kc = min(TOPK, c2.shape[0])
    np.put_along_axis(keep, np.argsort(c2, axis=1)[:, :kr], True, axis=1)
    np.put_along_axis(keep, np.argsort(c2, axis=0)[:kc, :], True, axis=0)
    model = c1_runs.calibrated(rows, known)
    names = [model.name(n) for n in known]
    out = np.full_like(c2, 2.0)
    for i, j in zip(*np.nonzero(keep)):
        c1 = c1_runs.align(rows[i].runs, names[j], model.s)
        out[i, j] = (c1 + c2[i, j]) / 2
    return out


def match(rows: list[RowF], known: list[str], max_cost: float = ACCEPT[0], margin: float = ACCEPT[1]) -> dict[str, str]:
    if not rows or not known:
        return {}
    pairs = c1v_q.accept(costs(rows, known), max_cost, margin)
    return {known[j]: rows[i].team for i, j in pairs if rows[i].team}


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    return match(feats(rgb), known)
