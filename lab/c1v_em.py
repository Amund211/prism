"""C1 variant: EM, no all-caps model"""

import numpy as np

import c1_runs
from c1_runs import EM_ACCEPT, Model, cost_matrix, glyph_scale, learn
from c_feats import RowF, assign_loo


def costs(rows: list[RowF], known: list[str], rounds: int = 1) -> np.ndarray:
    model = Model(glyph_scale(rows, known))
    cost = cost_matrix(rows, known, model)
    for _ in range(rounds):
        pairs = assign_loo(cost, *EM_ACCEPT)
        if len(pairs) < 3:
            break
        model = learn(rows, known, model, pairs)
        cost = cost_matrix(rows, known, model)
    return cost


_ = c1_runs
