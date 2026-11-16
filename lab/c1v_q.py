"""C1q: glyph-run alignment with a quantile-calibrated glyph model (width,
top, bottom), leave-one-out assignment margin, per-image cost limit."""

import numpy as np

from c1_runs import calibrated, cost_matrix
from c_feats import RowF, adaptive_max, assign_loo, feats

ACCEPT = (0.45, 0.07)
ADA = (4.0, 0.15)


def costs(rows: list[RowF], known: list[str]) -> np.ndarray:
    return cost_matrix(rows, known, calibrated(rows, known))


def accept(cost: np.ndarray, max_cost: float, margin: float) -> list[tuple[int, int]]:
    return assign_loo(cost, adaptive_max(cost, max_cost, *ADA), margin)


def match(rows: list[RowF], known: list[str], max_cost: float = ACCEPT[0], margin: float = ACCEPT[1]) -> dict[str, str]:
    if not rows or not known:
        return {}
    pairs = accept(costs(rows, known), max_cost, margin)
    return {known[j]: rows[i].team for i, j in pairs if rows[i].team}


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    return match(feats(rgb), known)
