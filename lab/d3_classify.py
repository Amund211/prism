"""D3: classify each glyph (nearest char, font from D1), then edit distance
between the read string and each name (rapidfuzz). Cheap matching step."""

import numpy as np
from rapidfuzz.distance import Levenshtein
from rapidfuzz.process import cdist

from d1_calib import build, finish
from d_core import char_dist

MAX_COST = 0.6  # tuned on train (d_tune.py); 0.7 lets a garbage read through
MARGIN = 0.1


def _read(ext, f, names) -> list[str]:
    chars = "".join(names)
    out = []
    for xr in ext.rows:
        if not xr.glyphs:
            out.append("")
            continue
        idx, D = char_dist(xr.glyphs, f, chars)
        inv = {i: c for c, i in idx.items()}
        out.append("".join(inv[int(i)] for i in D.argmin(axis=1)))
    return out


def _run(rgb, known):
    names = sorted(set(known))
    ext, f = build(rgb)
    if not ext or not ext.rows or not names:
        return ext, names, None
    read = _read(ext, f, names)
    return ext, names, np.asarray(cdist(read, names, scorer=Levenshtein.normalized_distance), float)


def costs(rgb: np.ndarray, known: list[str]):
    ext, names, C = _run(rgb, known)
    return ([r.team for r in ext.rows] if ext else []), names, C


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    ext, names, C = _run(rgb, known)
    return finish(ext, names, C, MAX_COST, MARGIN) if C is not None else {}
