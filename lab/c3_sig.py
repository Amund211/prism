"""C3: cheap signature match, no DP in Python. Per name and per row word:
total width (per-image scale), glyph count, and a string of glyph classes
(T tall, x short, d descender, D tall+descender, . small); rapidfuzz
Levenshtein on the class strings."""

import numpy as np
from rapidfuzz.distance import Levenshtein
from rapidfuzz.process import cdist

from c_feats import Glyph, RowF, assign_loo, char_glyph, feats

W_WIDTH, W_COUNT, W_SIG = 1.0, 0.5, 1.0
ACCEPT = (0.20, 0.08)


def cls(top: float, bot: float, h: float) -> str:
    if bot - top < 2.5:
        return "."  # punctuation, underscore, dots
    tall = top <= 1.0
    desc = bot >= 6.6
    return "D" if tall and desc else "T" if tall else "d" if desc else "x"


def name_sig(n: str) -> tuple[str, float, int]:
    gs = [char_glyph(c) for c in n]
    return "".join(cls(g.top, g.bot, 8) for g in gs), sum(g.w + 1 for g in gs) - 1, len(gs)


def row_sig(r: RowF) -> tuple[str, float, int]:
    return "".join(cls(g.top, g.bot, 8) for g in r.runs), r.width, len(r.runs)


def costs(rows: list[RowF], known: list[str]) -> np.ndarray:
    ns = [name_sig(n) for n in known]
    rs = [row_sig(r) for r in rows]
    nw = np.array([w for _, w, _ in ns])
    rw = np.array([w for _, w, _ in rs])
    nc = np.array([c for *_, c in ns], float)
    rc = np.array([c for *_, c in rs], float)
    lr = np.log(np.maximum(rw, 1))[:, None] - np.log(np.maximum(nw, 1))[None, :]
    # per-image scale: median of row-best log ratios
    s = np.median(lr[np.arange(len(rows)), np.abs(lr).argmin(axis=1)])
    wc = np.minimum(np.abs(lr - s) * 4, 1.5)
    cc = np.minimum(np.abs(rc[:, None] - nc[None, :]) / np.maximum(nc[None, :], 1), 1.0)
    sig = cdist([r for r, _, _ in rs], [n for n, _, _ in ns], scorer=Levenshtein.normalized_distance)
    return (W_WIDTH * wc + W_COUNT * cc + W_SIG * sig) / (W_WIDTH + W_COUNT + W_SIG)


def match(rows: list[RowF], known: list[str], max_cost: float = ACCEPT[0], margin: float = ACCEPT[1]) -> dict[str, str]:
    if not rows or not known:
        return {}
    pairs = assign_loo(costs(rows, known), max_cost, margin)
    return {known[j]: rows[i].team for i, j in pairs if rows[i].team}


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    return match(feats(rgb), known)


_ = Glyph
