"""I4 fast cascade: h4-style fast union (g2 + d3 + c5 vote), then the CRNN
for names still unknown. I4_LOO set -> leave-own-font-out model."""

import os

import numpy as np

from h_common import fast_union
from i4_rec import loo_model, match

LOO = bool(os.environ.get("I4_LOO"))


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    out, _, tab, prows = fast_union(rgb, known)
    left = [n for n in known if n not in out]
    if left and tab is not None:
        m = loo_model(rgb, tab, prows, known) if LOO else "full"
        out.update(match(rgb, known, tab, prows, m, only=left))
    return out
