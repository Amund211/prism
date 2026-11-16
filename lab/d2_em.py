"""D2: D1, then self-training: glyphs of confident matches become samples."""

import numpy as np

from common import assign
from d1_calib import build, finish
from d_core import cost_matrix, learn_from

ROUNDS = 2
SEED_COST = 0.25
SEED_MARGIN = 0.1


def _run(rgb, known):
    names = sorted(set(known))
    ext, f = build(rgb)
    if not ext or not ext.rows or not names:
        return ext, names, None
    C, paths = cost_matrix(ext, names, f)
    for _ in range(ROUNDS):
        pairs = assign(C, SEED_COST, SEED_MARGIN)
        if not pairs or learn_from(ext, f, pairs, names, paths) == 0:
            break
        C, paths = cost_matrix(ext, names, f)
    return ext, names, C


def costs(rgb: np.ndarray, known: list[str]):
    ext, names, C = _run(rgb, known)
    return ([r.team for r in ext.rows] if ext else []), names, C


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    ext, names, C = _run(rgb, known)
    return finish(ext, names, C, 0.45, 0.1) if C is not None else {}
