"""Split a tab row into words; colour and glyph mask per word."""

from dataclasses import dataclass

import numpy as np

from rows import Row, runs_of

# vanilla text colours of the 8 Bed Wars teams
PALETTE = {
    "red": (255, 85, 85),
    "blue": (85, 85, 255),
    "green": (85, 255, 85),
    "yellow": (255, 255, 85),
    "aqua": (85, 255, 255),
    "white": (255, 255, 255),
    "pink": (255, 85, 255),
    "gray": (85, 85, 85),  # dark gray; respawning names are light gray, no letter
}
LETTER = {"red": "R", "blue": "B", "green": "G", "yellow": "Y", "aqua": "A", "white": "W", "pink": "P", "gray": "S"}
TEAM_ORDER = ["aqua", "blue", "gray", "green", "pink", "red", "white", "yellow"]


@dataclass
class Word:
    x0: int
    x1: int
    spans: list[tuple[int, int]]  # glyph column spans, image x
    color: tuple[int, int, int]  # dominant text colour
    shadow: tuple[int, int, int]  # dominant shadow colour
    mask: np.ndarray  # bool, 8k x (x1 - x0), text pixels of this colour


def text_colors(px: np.ndarray, min_count: int) -> np.ndarray:
    vals, counts = np.unique(px, axis=0, return_counts=True)
    return vals[counts >= min_count]


def words(
    rgb: np.ndarray, smask: np.ndarray, row: Row, gap: float = 2.5, tol: int = 10
) -> list[Word]:
    k = row.k
    y, x0, x1 = row.y, row.x0, row.x1
    band = rgb[y : y + 8 * k, x0:x1].astype(np.int16)
    sm = smask[y : y + 8 * k, x0:x1]
    cols = text_colors(band[sm], max(3, 2 * k * k))
    if len(cols) == 0:
        return []
    d = np.abs(band[:, :, None, :] - cols[None, None, :, :]).max(axis=3)
    idx = d.argmin(axis=2)
    tm = d.min(axis=2) <= tol
    spans = runs_of(tm.any(axis=0))
    if not spans:
        return []
    groups: list[list[tuple[int, int]]] = [[spans[0]]]
    for a, b in spans[1:]:
        if a - groups[-1][-1][1] >= gap * k:
            groups.append([])
        groups[-1].append((a, b))
    out = []
    for g in groups:
        a, b = g[0][0], g[-1][1]
        wt = tm[:, a:b]
        ws = sm[:, a:b]
        if ws.sum() < 2 * k or not wt.any():
            continue
        cnt = np.bincount(idx[:, a:b][wt], minlength=len(cols))
        # shaded fonts (texel x colour): the brightest frequent shade is the colour
        frequent = np.flatnonzero(cnt >= max(1, cnt.max() // 4))
        ci = frequent[cols[frequent].sum(axis=1).argmax()]
        color = tuple(int(c) for c in cols[ci])
        # pixels of this colour or a darker shade of it
        main = cols[ci].astype(float) + 1
        ratio = cols.astype(float) / main
        shade = (ratio.max(axis=1) - ratio.min(axis=1) <= 0.12) & (ratio.max(axis=1) <= 1.05)
        mask = wt & shade[idx[:, a:b]]
        yy, xx = np.nonzero(mask & ws)
        sy = np.clip(y + yy + k, 0, rgb.shape[0] - 1)
        sx = np.clip(x0 + a + xx + k, 0, rgb.shape[1] - 1)
        sh = rgb[sy, sx]
        shadow = tuple(int(c) for c in np.median(sh, axis=0)) if len(sh) else (0, 0, 0)
        out.append(Word(x0 + a, x0 + b, [(x0 + p, x0 + q) for p, q in g], color, shadow, mask))
    return out


def nearest_team(color: tuple[int, int, int], max_dist: float = 60) -> str | None:
    c = np.array(color, float)
    best, bd = None, 1e9
    for t, p in PALETTE.items():
        dd = float(np.linalg.norm(c - np.array(p)))
        if dd < bd:
            best, bd = t, dd
    return best if bd <= max_dist else None


def glyph_runs(word: Word) -> list[int]:
    return [b - a for a, b in runs_of(word.mask.any(axis=0))]
