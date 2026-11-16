"""H1: union of g2, d3_classify, c5_fast; disagreement gives no team."""

import numpy as np

from h_common import fast_union


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    return fast_union(rgb, known)[0]
