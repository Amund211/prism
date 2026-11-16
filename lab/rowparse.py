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


def text_colors(px: np.ndarray, min_count: int, top: int = 16) -> np.ndarray:
    """Colours with >= min_count shadow-tested pixels (the top most common)"""
    if len(px) == 0:
        return px.reshape(0, 3)
    key = (px[:, 0].astype(np.int32) << 16) | (px[:, 1].astype(np.int32) << 8) | px[:, 2]
    vals, counts = np.unique(key, return_counts=True)
    keep = counts >= min_count
    vals, counts = vals[keep], counts[keep]
    vals = vals[np.argsort(-counts, kind="stable")[:top]]
    return np.stack([(vals >> 16) & 255, (vals >> 8) & 255, vals & 255], axis=1).astype(px.dtype)


@dataclass
class RowText:
    """Text pixels of one row: glyph column spans (band x) and colour index"""

    row: Row
    cols: np.ndarray  # text colours
    idx: np.ndarray  # per pixel: nearest text colour
    tm: np.ndarray  # per pixel: is text
    sm: np.ndarray  # shadow mask band
    spans: list[tuple[int, int]]


def row_text(rgb: np.ndarray, smask: np.ndarray, row: Row, tol: int = 10) -> RowText | None:
    k = row.k
    y, x0, x1 = row.y, row.x0, row.x1
    band = rgb[y : y + 8 * k, x0:x1].astype(np.int16)
    sm = smask[y : y + 8 * k, x0:x1]
    cols = text_colors(band[sm], max(3, 2 * k * k))
    if len(cols) == 0:
        return None
    # only pixels bright enough to be within tol of a text colour
    vmax = band.max(axis=2)
    cand = vmax >= int(cols.max(axis=1).min()) - tol
    d = np.abs(band[cand][:, None, :] - cols[None, :, :]).max(axis=2)
    idx = np.zeros(vmax.shape, np.intp)
    tm = np.zeros(vmax.shape, bool)
    if len(d):
        idx[cand] = d.argmin(axis=1)
        tm[cand] = d.min(axis=1) <= tol
    spans = runs_of(tm.any(axis=0))
    if not spans:
        return None
    return RowText(row, cols, idx, tm, sm, spans)


def gaps(rt: RowText) -> list[int]:
    return [p - b for (_, b), (p, _) in zip(rt.spans, rt.spans[1:])]


def words(
    rgb: np.ndarray, smask: np.ndarray, row: Row, gap: float = 2.5, tol: int = 10, rt: RowText | None = None
) -> list[Word]:
    """Split the row at gaps >= gap * k (pass rt to reuse row_text)"""
    rt = rt or row_text(rgb, smask, row, tol)
    if rt is None:
        return []
    k = row.k
    y, x0 = row.y, row.x0
    cols, idx, tm, sm, spans = rt.cols, rt.idx, rt.tm, rt.sm, rt.spans
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
