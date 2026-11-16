"""C1 variant: all-caps model only, no EM"""

import c1_runs
from c_feats import RowF


def costs(rows: list[RowF], known: list[str]):
    return c1_runs.costs(rows, known, rounds=0)
