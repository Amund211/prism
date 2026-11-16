"""Shared bits for the OCR matchers: crops and name matching."""

import numpy as np
from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

from common import PRow, assign


def candidates(prows: list[PRow]) -> list[PRow]:
    """Rows with a name word; drop duplicates (same word found twice)"""
    seen = set()
    out = []
    for p in prows:
        if p.name is None:
            continue
        key = (p.row.y, p.name.x0)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def name_crop(p: PRow, scale: int = 5, pad: int = 12) -> np.ndarray:
    """Black text on white, font px upscaled by `scale` (uint8)"""
    k = p.row.k
    m = p.name.mask[::k, ::k] if k > 1 else p.name.mask
    m = m.repeat(scale, axis=0).repeat(scale, axis=1)
    out = np.full((m.shape[0] + 2 * pad, m.shape[1] + 2 * pad), 255, np.uint8)
    out[pad : pad + m.shape[0], pad : pad + m.shape[1]][m] = 0
    return out


def sim(a: str, b: str) -> float:
    """0..1 similarity, case-insensitive plus a bit of case"""
    s1 = fuzz.ratio(a.lower(), b.lower()) / 100
    s2 = fuzz.ratio(a, b) / 100
    return 0.8 * s1 + 0.2 * s2


def match(texts: list[str], teams: list[str | None], known: list[str],
          max_cost: float = 0.35, margin: float = 0.12) -> dict[str, str]:
    if not texts or not known:
        return {}
    pairs = list(dict.fromkeys((t, tm) for t, tm in zip(texts, teams) if t))
    texts = [p[0] for p in pairs]
    teams = [p[1] for p in pairs]
    if not texts:
        return {}
    cost = np.array([[1 - sim(t, n) if t else 1.0 for n in known] for t in texts])
    out = {}
    for i, j in assign(cost, max_cost=max_cost, margin=margin):
        if teams[i]:
            out[known[j]] = teams[i]
    return out


__all__ = ["name_crop", "sim", "match", "Levenshtein"]
