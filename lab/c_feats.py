"""Shape worker: geometric features of name words and of names (vanilla font)."""

import pickle
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import numpy as np

import font
from common import PRow, parse
from rows import runs_of

CACHE = Path(__file__).parent / "results" / "shape_cache"


@dataclass
class Glyph:
    w: float  # width, font px
    top: float  # first ink row, font px (0 = cap height)
    bot: float  # last ink row (6 = baseline row, 7 = descender)
    ink: float  # ink pixels / (w * 8), font px units


@dataclass
class RowF:
    team: str | None
    width: float  # name word width, font px
    runs: list[Glyph]
    profile: np.ndarray  # ink per column, image px (normalised by k)
    k: int
    y: int = 0
    x0: int = 0


@cache
def char_glyph(c: str) -> Glyph:
    g = font.load()
    gl = g.get(c, g["?"])
    rows = np.flatnonzero(gl.any(axis=1))
    if gl.shape[1] == 0 or len(rows) == 0:
        return Glyph(gl.shape[1], 3, 3, 0)
    return Glyph(gl.shape[1], float(rows[0]), float(rows[-1]), gl.sum() / (gl.shape[1] * 8))


@cache
def name_glyphs(name: str) -> tuple[Glyph, ...]:
    # space-less names; chars with zero width are dropped
    return tuple(char_glyph(c) for c in name)


@cache
def name_profile(name: str) -> np.ndarray:
    """3 x width: ink per column in the bands of RowF.profile (vanilla font)"""
    r = font.render(name, 1)
    return np.stack([r[:2].sum(axis=0), r[2:7].sum(axis=0), r[7:].sum(axis=0)]).astype(np.float32)


def row_feats(p: PRow, k: int) -> RowF | None:
    w = p.name
    if w is None:
        return None
    m = w.mask
    runs = []
    for a, b in runs_of(m.any(axis=0)):
        rows = np.flatnonzero(m[:, a:b].any(axis=1))
        runs.append(Glyph((b - a) / k, rows[0] / k, rows[-1] / k, m[:, a:b].sum() / ((b - a) * 8 * k)))
    # ink per column in 3 bands: ascender/cap rows 0-1, body 2-6, descender 7
    prof = np.stack(
        [m[: 2 * k].sum(axis=0), m[2 * k : 7 * k].sum(axis=0), m[7 * k :].sum(axis=0)]
    ).astype(np.float32) / k
    return RowF(p.team, (w.x1 - w.x0) / k, runs, prof, k, p.row.y, w.x0)


def feats(rgb: np.ndarray) -> list[RowF]:
    tab, prows = parse(rgb)
    if tab is None:
        return []
    out: list[RowF] = []
    seen = set()
    for p in prows:
        f = row_feats(p, tab.k)
        if f is None or (f.y, f.x0) in seen:  # same word found twice
            continue
        seen.add((f.y, f.x0))
        out.append(f)
    return out


def adaptive_max(cost: np.ndarray, max_cost: float, a: float = 2.5, b: float = 0.1) -> float:
    """Per-image cost limit: a clean font matches near 0, so a 0.2 match is
    suspect there; a custom font has higher costs for all true pairs"""
    best = np.sort(cost.min(axis=1))
    med = float(np.median(best[: max(1, len(best) * 2 // 3)]))
    return min(max_cost, a * med + b)


def assign_loo(cost: np.ndarray, max_cost: float, margin: float) -> list[tuple[int, int]]:
    """Hungarian; keep a pair if it is cheap and if the best assignment without
    it costs at least `margin` more (other rows / names re-solved)."""
    from scipy.optimize import linear_sum_assignment

    if cost.size == 0:
        return []
    # a row or name may stay unassigned, at cost max_cost / 2 each
    c = np.minimum(cost, 10.0)
    n, m = c.shape
    full = np.full((n + m, m + n), max_cost / 2)
    full[:n, :m] = c
    full[n:, m:] = 0
    r, col = linear_sum_assignment(full)
    base = full[r, col].sum()
    out = []
    for i, j in zip(r, col):
        if i >= n or j >= m or c[i, j] > max_cost:
            continue
        f2 = full.copy()
        f2[i, j] = 1e6
        r2, c2 = linear_sum_assignment(f2)
        if f2[r2, c2].sum() - base >= margin:
            out.append((int(i), int(j)))
    return out


def cached_feats(name: str, rgb_loader) -> list[RowF]:
    """Dev only: parse once per image (pipeline changes: delete the cache)"""
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{name}.pkl"
    if f.exists():
        return pickle.loads(f.read_bytes())
    out = feats(rgb_loader(name))
    f.write_bytes(pickle.dumps(out))
    return out
