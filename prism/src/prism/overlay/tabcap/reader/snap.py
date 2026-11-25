"""Snap read names to the known names (one-to-one).

Port of lab tbench.snap (cost = i4_rec.cost, assignment = common.assign).
Own Levenshtein (no rapidfuzz): names are <= 16 chars, so the plain O(n m)
loop is fast enough, and it keeps the native deps of the build small.
"""

from collections.abc import Sequence

import numpy as np
from scipy.optimize import linear_sum_assignment  # type: ignore[import-untyped]

from prism.overlay.tabcap.reader.front import clean
from prism.overlay.tabcap.reader.front.guiscale import Array

MAX_COST = 0.34
MARGIN = 0.08
CASE_PENALTY = 0.04


def levenshtein(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def normalized(a: str, b: str) -> float:
    """Levenshtein / longer length, 0 for two empty strings (as rapidfuzz)"""
    n = max(len(a), len(b))
    return levenshtein(a, b) / n if n else 0.0


def cost(text: str, name: str) -> float:
    t = clean(text)
    return min(normalized(t, name), normalized(t.lower(), name.lower()) + CASE_PENALTY)


def assign(c: Array, max_cost: float, margin: float) -> list[tuple[int, int]]:
    """Hungarian reads x names; keep pairs under max_cost with a clear margin
    over the next-best name for that read and next-best read for that name"""
    rows, cols = linear_sum_assignment(c)
    out = []
    for i, j in zip(rows, cols):
        v = c[i, j]
        if v > max_cost:
            continue
        row_alt = np.delete(c[i], j).min() if c.shape[1] > 1 else np.inf
        col_alt = np.delete(c[:, j], i).min() if c.shape[0] > 1 else np.inf
        if min(row_alt, col_alt) - v < margin:
            continue
        out.append((int(i), int(j)))
    return out


def snap(names: Sequence[str], known: Sequence[str]) -> list[tuple[int, int]]:
    """(index in names, index in known) for each read name that snaps"""
    if not names or not known:
        return []
    c = np.array([[cost(n, k) for k in known] for n in names])
    return assign(c, MAX_COST, MARGIN)
