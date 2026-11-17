"""Algorithm D: learn the user's font from the image, then match again.

B renders names with a generic font. Rows B is sure about give (text,
image) pairs. The image of a row is linear in the glyph bitmaps:

    image = Wy @ canvas @ Wx.T   (area scaling from GUI px to screen px)

so least squares gives each char's bitmap at GUI resolution, for this
user's font, sharp or blurred. Then all rows are scored again with the
learned font (generic font for chars not seen yet), and we repeat.
A font learned from earlier screenshots can be passed in (`font`).
"""

import sys
from pathlib import Path
from typing import Sequence

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tabsoft as tb  # noqa: E402
from glyphs import GLYPHS, UNKNOWN  # noqa: E402

Font = dict[str, np.ndarray]  # char -> 8 x w bitmap, GUI px
STRETCHES = (0.92, 1.0, 1.08)
SHIFTS = (-1, 0, 1)
ITERATIONS = 1
MIN_PAIRS = 3  # need this many sure rows to learn


def _glyph(font: Font, ch: str) -> np.ndarray:
    return font.get(ch, GLYPHS.get(ch, UNKNOWN))


def canvas(name: str, font: Font) -> tuple[np.ndarray, list[int]]:
    """8 x W GUI bitmap and the x offset of each char."""
    cols, offs, x = [], [], 0
    for ch in name:
        g = GLYPHS.get(ch, UNKNOWN)  # widths from the generic font
        offs.append(x)
        cols += [_glyph(font, ch)[:, : g.shape[1]], np.zeros((8, 1), np.float32)]
        x += g.shape[1] + 1
    return np.concatenate(cols[:-1], axis=1), offs


def weights(n_out: int, start: float, scale: float, n_in: int) -> np.ndarray:
    """W[j, i] = part of screen px j covered by GUI cell i (area scaling)."""
    j = np.arange(n_out, dtype=np.float32)[:, None]
    c0 = start + np.arange(n_in, dtype=np.float32)[None, :] * scale
    return np.clip(np.minimum(j + 1, c0 + scale) - np.maximum(j, c0), 0, None)


def _ncc(a: np.ndarray, b: np.ndarray) -> float:
    a = a - a.mean()
    b = b - b.mean()
    d = float(np.sqrt((a * a).sum() * (b * b).sum()))
    return float((a * b).sum()) / d if d > 0 else 0.0


MAX_GUI_W = 16 * 7  # widest name in GUI px (16 chars)
_PLACES = [(st, dx) for st in STRETCHES for dx in SHIFTS]


def _row_weights(row: tb.SoftRow) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """Per row, cached: Wy per dy, Wx per (stretch, dx), centered alpha."""
    cache = row.__dict__.get("_w")
    if cache is None:
        u = (row.base - row.cap) / 7
        H, W = row.alpha.shape
        Wy = np.stack([weights(H, row.cap - row.oy + dy, u, 8) for dy in SHIFTS])
        Wx = np.stack(
            [weights(W, row.x0 - row.ox + dx, u * st, MAX_GUI_W) for st, dx in _PLACES]
        )
        a = row.alpha - row.alpha.mean()
        cache = (Wy, Wx, a, float(np.sqrt((a * a).sum())))
        row.__dict__["_w"] = cache
    return cache


def score(row: tb.SoftRow, name: str, font: Font) -> tuple[float, tuple]:
    """Best NCC (as tabsoft score) and its (stretch, dx, dy)."""
    G, _ = canvas(name, font)
    Wy, Wx, a, an = _row_weights(row)
    g = min(G.shape[1], MAX_GUI_W)
    # All placements at once: (dy, place, H, W).
    P = np.einsum("dha,ag,kwg->dkhw", Wy, G[:, :g], Wx[:, :, :g], optimize=True)
    P = P - P.mean(axis=(2, 3), keepdims=True)
    num = np.einsum("dkhw,hw->dk", P, a)
    den = np.sqrt((P * P).sum(axis=(2, 3))) * an
    ncc = np.where(den > 0, num / np.maximum(den, 1e-9), 0)
    d, k = np.unravel_index(int(np.argmax(ncc)), ncc.shape)
    st, dx = _PLACES[k]
    return tb.SCALE * (float(ncc[d, k]) - 1), (st, dx, SHIFTS[d])


def learn(pairs: list[tuple[tb.SoftRow, str, tuple]]) -> Font:
    """Least-squares glyph bitmaps from (row, name, placement) pairs."""
    chars = sorted({c for _, n, _ in pairs for c in n})
    width = {c: GLYPHS.get(c, UNKNOWN).shape[1] for c in chars}
    base, nv = {}, 0
    for c in chars:
        base[c] = nv
        nv += 8 * width[c]
    AtA = np.zeros((nv, nv))
    Atb = np.zeros(nv)
    for row, name, (st, dx, dy) in pairs:
        _, offs = canvas(name, {})
        Wg = offs[-1] + width[name[-1]]
        u = (row.base - row.cap) / 7
        H, W = row.alpha.shape
        Wy = weights(H, row.cap - row.oy + dy, u, 8)
        Wx = weights(W, row.x0 - row.ox + dx, u * st, Wg)
        K = np.einsum("ha,wb->hwab", Wy, Wx).reshape(H * W, 8 * Wg)
        # Local vars of this row -> global var index; GUI cell -> local var.
        idx = sorted({base[c] + k for c in set(name) for k in range(8 * width[c])})
        loc = {g: k for k, g in enumerate(idx)}
        P = np.zeros((8 * Wg, len(idx)))
        for ch, o in zip(name, offs):
            for iy in range(8):
                for ix in range(width[ch]):
                    P[iy * Wg + o + ix, loc[base[ch] + iy * width[ch] + ix]] += 1
        M = K @ P
        o = row.alpha.reshape(-1)
        ii = np.array(idx)
        AtA[np.ix_(ii, ii)] += M.T @ M
        Atb[ii] += M.T @ o
    # Ridge toward the generic font, so rarely seen chars stay sensible.
    prior = np.concatenate([GLYPHS.get(c, UNKNOWN).reshape(-1) for c in chars])
    lam = 0.05 * float(np.mean(np.diag(AtA))) + 1e-3
    theta = np.linalg.solve(AtA + lam * np.eye(nv), Atb + lam * prior)
    return {
        c: np.clip(theta[base[c] : base[c] + 8 * width[c]], 0, 1).reshape(8, width[c])
        for c in chars
    }


def read_teams(
    rgb: np.ndarray,
    known: Sequence[str],
    fixed: dict[str, str] | None = None,
    font: Font | None = None,
    grid: bool = False,
) -> tuple[dict[str, str], Font]:
    """({name: team}, learned font). fixed: teams already known (e.g. A).

    grid: also look for rows on the tab grid (approach E, tablayout.py).
    """
    rows = tb.find_rows(rgb)
    names = list(known)
    if grid and names:
        import tablayout

        widest = max(canvas(n, {})[0].shape[1] for n in names)
        rows = tablayout.grid_rows(rgb, rows, widest)
    font = dict(font or {})
    if not rows or not names:
        return {}, font
    out: dict[str, int] = {}
    for it in range(ITERATIONS + 1):
        res = [[score(r, n, font) for n in names] for r in rows]
        S = np.array([[s for s, _ in line] for line in res])
        out = tb.decide(rows, names, S, fixed)
        if it == ITERATIONS or len(out) < MIN_PAIRS:
            break
        j = {n: k for k, n in enumerate(names)}
        pairs = [(rows[i], n, res[i][j[n]][1]) for n, i in out.items()]
        font = {**font, **learn(pairs)}
    return {n: rows[i].team for n, i in out.items()}, font
