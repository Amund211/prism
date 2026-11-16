"""D4: D3 (classify + edit distance), plus one self-training round: rows
that match a name with the same glyph count give their glyphs as samples."""

import numpy as np
from rapidfuzz.distance import Levenshtein
from rapidfuzz.process import cdist

from common import assign
from d1_calib import build, finish
from d3_classify import _read

MAX_COST = 0.7
MARGIN = 0.15
SEED_COST = 0.3


def _run(rgb, known):
    names = sorted(set(known))
    ext, f = build(rgb)
    if not ext or not ext.rows or not names:
        return ext, names, None
    read = _read(ext, f, names)
    C = np.asarray(cdist(read, names, scorer=Levenshtein.normalized_distance), float)
    learned = 0
    for i, j in assign(C, SEED_COST, MARGIN):
        g = ext.rows[i].glyphs
        if len(g) == len(names[j]):
            for c, gl in zip(names[j], g):
                f.add(c, gl)
                learned += 1
    if learned:
        read = _read(ext, f, names)
        C = np.asarray(cdist(read, names, scorer=Levenshtein.normalized_distance), float)
    return ext, names, C


def costs(rgb: np.ndarray, known: list[str]):
    ext, names, C = _run(rgb, known)
    return ([r.team for r in ext.rows] if ext else []), names, C


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    ext, names, C = _run(rgb, known)
    return finish(ext, names, C, MAX_COST, MARGIN) if C is not None else {}
