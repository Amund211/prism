"""Shared pipeline parts: tab rows -> parsed rows; assignment helpers."""

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linear_sum_assignment

from rowparse import Word, nearest_team, words
from rows import Row, Tab, find_tab, runs_of


@dataclass
class PRow:
    row: Row
    letter: Word | None
    name: Word | None
    team: str | None  # from the letter colour; None if no letter
    words: list[Word]


def _close(a: tuple[int, ...], b: tuple[int, ...], tol: int = 24) -> bool:
    return max(abs(x - y) for x, y in zip(a, b)) <= tol


def parse(rgb: np.ndarray, tab: Tab | None = None) -> tuple[Tab | None, list[PRow]]:
    tab = tab or find_tab(rgb)
    if tab is None:
        return None, []
    out = []
    k = tab.k
    for r in tab.rows:
        ws = words(rgb, tab.mask, r)
        if not ws:
            continue
        # names have >= 3 chars; head icons can give 1-2 spans
        name = next((w for w in ws if len(w.spans) >= 3 and w.x1 - w.x0 >= 9 * k), None)
        letter = find_letter(rgb, r, name) if name else None
        team = team_of(name) if letter and name else None
        out.append(PRow(r, letter, name, team, ws))
    return tab, out


def team_of(w: Word) -> str | None:
    """Palette team of the text colour; else of the shadow x4 (packs that
    remap text colours keep the vanilla shadow)"""
    t = nearest_team(w.color)
    if t is None:
        t = nearest_team(tuple(min(255, 4 * c + 2) for c in w.shadow), max_dist=50)
    return t


def shade_of(px: np.ndarray, color: tuple[int, int, int], lo: float = 0.55) -> np.ndarray:
    """Pixels that are the colour, or a darker shade of it (shaded fonts)"""
    c = np.array(color, np.float32)
    strong = c >= 40  # ratios of near-zero channels are noise
    p = px.astype(np.float32)
    ratio = p[..., strong] / c[strong]
    hi_, lo_ = ratio.max(axis=-1), ratio.min(axis=-1)
    ok = (hi_ - lo_ <= 0.12) & (lo_ >= lo) & (hi_ <= 1.05)
    if not strong.all():
        ok &= (p[..., ~strong] <= 48).all(axis=-1)
    return ok


def find_letter(rgb: np.ndarray, r: Row, name: Word, tol: int = 24) -> Word | None:
    """A glyph in the name colour just left of the name (the team letter).
    Checks colour, not the word split, so client icons next to it do not matter."""
    k = r.k
    a = max(0, name.x0 - 12 * k)
    b = name.x0 - 2 * k
    if b <= a:
        return None
    band = rgb[r.y : r.y + 8 * k, a:b]
    m = shade_of(band, name.color)
    spans = runs_of(m.sum(axis=0) >= k)
    if not spans:
        return None
    p, q = spans[-1]
    while len(spans) >= 2 and p - spans[-2][1] < k + 1:  # glyph parts
        spans.pop()
        p = spans[-1][0]
    rows_on = np.flatnonzero(m[:, p:q].any(axis=1))
    if not (2 * k <= q - p <= 8 * k) or len(rows_on) == 0 or rows_on[-1] - rows_on[0] < 5 * k:
        return None
    return Word(a + p, a + q, [(a + p, a + q)], name.color, name.shadow, m[:, p:q])


def assign(cost: np.ndarray, max_cost: float, margin: float) -> list[tuple[int, int]]:
    """Hungarian rows x names; keep pairs under max_cost with a clear margin
    over the next-best name for that row and next-best row for that name"""
    if cost.size == 0:
        return []
    r, c = linear_sum_assignment(cost)
    out = []
    for i, j in zip(r, c):
        v = cost[i, j]
        if v > max_cost:
            continue
        row_alt = np.delete(cost[i], j).min() if cost.shape[1] > 1 else np.inf
        col_alt = np.delete(cost[:, j], i).min() if cost.shape[0] > 1 else np.inf
        if min(row_alt, col_alt) - v < margin:
            continue
        out.append((int(i), int(j)))
    return out
