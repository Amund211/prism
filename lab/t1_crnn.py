"""T1: j4 finder chain + parse, i4 CRNN greedy read of each name region.
Team from the parsed letter / letter slot. Reads that are not a valid
username are dropped."""

import numpy as np

from g_match import regions_of
from i4_rec import read_crops
from i4_synth import norm_crop
from tl_front import clean, front, valid


def reads(rgb: np.ndarray):
    """[(text, prow)] for every name region"""
    _, tab, prows = front(rgb)
    if tab is None:
        return []
    k = tab.k
    regions = regions_of(rgb, prows, k)
    texts = read_crops([norm_crop(rgb, r.prow.row.y, r.x0, r.x1, k) for r in regions], "full")
    return [(clean(t), r.prow) for t, r in zip(texts, regions)]


def read_tab(rgb: np.ndarray) -> list[tuple[str, str | None]]:
    out = {}
    for t, p in reads(rgb):
        if valid(t) and t not in out:
            out[t] = p.team
    return list(out.items())
