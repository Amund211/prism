"""C1q + all-caps model: per image keep the model (normal / all caps) whose
best row costs are lower."""

import numpy as np

import c1v_q
from c1_runs import calibrated, cost_matrix
from c_feats import RowF, feats


def score(cost: np.ndarray) -> float:
    best = np.sort(cost.min(axis=1))
    return float(best[: max(1, len(best) * 2 // 3)].mean())


def costs(rows: list[RowF], known: list[str]) -> np.ndarray:
    a = cost_matrix(rows, known, calibrated(rows, known))
    b = cost_matrix(rows, known, calibrated(rows, known, caps=True))
    return a if score(a) <= score(b) else b


def match(rows: list[RowF], known: list[str]) -> dict[str, str]:
    if not rows or not known:
        return {}
    pairs = c1v_q.accept(costs(rows, known), *c1v_q.ACCEPT)
    return {known[j]: rows[i].team for i, j in pairs if rows[i].team}


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    return match(feats(rgb), known)
