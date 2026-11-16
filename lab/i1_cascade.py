"""I1 cascade: h2b, then i1 colour-layer OCR (shape letter check), scales 5/3/8."""

import numpy as np

import h2b_cascade
import h5_layer
import i1_layer

h5_layer.SCALES = (5, 3, 8)
i1_layer.MIN_IOU, i1_layer.MIN_MARGIN = 0.6, 0.0


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    out = h2b_cascade.read_teams(rgb, known)
    left = [n for n in known if n not in out]
    if left:
        out.update(i1_layer.match(i1_layer.layer_lines(rgb, left), left))
    return out
