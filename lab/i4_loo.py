"""I4: CRNN reader alone; the model never saw the image's own font family."""

import numpy as np

from common import parse
from i4_rec import loo_model, match


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    tab, prows = parse(rgb)
    if tab is None:
        return {}
    return match(rgb, known, tab, prows, loo_model(rgb, tab, prows, known))
