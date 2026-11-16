"""Ablation of D3: vanilla templates only (no header / footer calibration)."""

import numpy as np
from rapidfuzz.distance import Levenshtein
from rapidfuzz.process import cdist

from d3_classify import _read
from d_core import Font, extract


def costs(rgb: np.ndarray, known: list[str]):
    names = sorted(set(known))
    ext = extract(rgb)
    if not ext or not ext.rows or not names:
        return [], names, None
    read = _read(ext, Font(), names)
    C = cdist(read, names, scorer=Levenshtein.normalized_distance)
    return [r.team for r in ext.rows], names, np.asarray(C, float)
