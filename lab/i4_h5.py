"""I4 after h5_cascade_ms: CRNN for names still unknown."""

import numpy as np

import h5_cascade_ms
from common import parse
from i4_rec import match


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    out = h5_cascade_ms.read_teams(rgb, known)
    left = [n for n in known if n not in out]
    if left:
        tab, prows = parse(rgb)
        out.update(match(rgb, known, tab, prows, "full", only=left))
    return out
