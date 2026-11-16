"""H5 cascade: h2b, then colour-layer OCR (h5_layer) for names still unknown."""

import numpy as np

import h2b_cascade
import h5_layer


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    out = h2b_cascade.read_teams(rgb, known)
    left = [n for n in known if n not in out]
    if left:
        out.update(h5_layer.match(h5_layer.layer_lines(rgb, left), left))
    return out
