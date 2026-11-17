"""Approach E: find all tab rows from the grid the sure rows make.

Tab rows have one pitch (9 GUI px) and the team letters are in one
column (Lunar's icon moves some letters right). Rows B finds give the
pitch, the letter column and the letter -> name offset. At every grid
place we try the 8 bold team letters; where one fits, we add a row.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tabsoft as tb  # noqa: E402

MIN_LETTER = 0.35  # the place is known from the grid, so a bit looser
MAX_EMPTY = 3  # stop after this many grid places without a row


def _best_letter(cls: np.ndarray, cap: int, u: float, xs: list[int]) -> tuple[float, int, int]:
    """(score, team index, letter x) of the best team letter near xs."""
    h = round(7 * u)
    best = (-1.0, -1, -1)
    x0, x1 = max(0, xs[0]), min(cls.shape[1], xs[-1] + h)
    box = cls[max(0, cap) : cap + h, x0:x1]
    for t in range(len(tb.TEAM_NAMES)):
        m = box == t
        if m.sum() < 0.15 * h * h:
            continue
        # Only try left edges of this color.
        colhas = m.any(axis=0)
        edges = [x0 + i for i in range(len(colhas)) if colhas[i] and (i == 0 or not colhas[i - 1])]
        for x in edges:
            if not xs[0] <= x <= xs[-1]:
                continue
            seg = tb.Seg(t, x, x + round(7 * u), cap, cap + h)
            s = tb.letter_score(cls, seg)
            if s > best[0]:
                best = (s, t, x)
    return best


def grid_rows(rgb: np.ndarray, rows: list[tb.SoftRow], max_name_w: float) -> list[tb.SoftRow]:
    """rows + rows found on the grid. max_name_w: widest name, GUI px."""
    if not rows:
        return rows
    caps = sorted(r.cap for r in rows)
    u = float(np.median([(r.base - r.cap) / 7 for r in rows]))
    pitch = 9 * u
    # Refine the pitch from the gaps between found rows.
    steps = [(b - a) / round((b - a) / pitch) for a, b in zip(caps, caps[1:]) if b - a > 0.5 * pitch]
    if steps:
        pitch = float(np.median(steps))
    lxs = sorted({r.lx for r in rows})
    col = min(lxs)
    offs = [r.x0 - r.lx for r in rows]
    off = int(np.median(offs))
    cls = tb.classify(rgb)
    H, W = cls.shape

    have = {round((r.cap - caps[0]) / pitch) for r in rows}
    out = list(rows)
    for direction in (-1, 1):
        k = 0 if direction < 0 else round((caps[-1] - caps[0]) / pitch)
        empty = 0
        while empty < MAX_EMPTY:
            k += direction
            if k in have:
                empty = 0
                continue
            cap = round(caps[0] + k * pitch)
            if cap < 0 or cap + 9 * u >= H:
                break
            # Letter: at the column, or after a Lunar icon (up to ~10 GUI px).
            xs = list(range(col - 1, min(W, col + round(11 * u)) + 1))
            s, t, lx = _best_letter(cls, cap, u, xs)
            if s < MIN_LETTER:
                empty += 1
                continue
            empty = 0
            x0 = lx + off
            x1 = x0 + round(max_name_w * u * 1.15) + 4
            out.append(tb.make_row(rgb, cls, t, cap, cap + round(7 * u), lx, x0, x1))
    # Places between found rows.
    for k in range(1, round((caps[-1] - caps[0]) / pitch)):
        if k in have:
            continue
        cap = round(caps[0] + k * pitch)
        xs = list(range(col - 1, min(W, col + round(11 * u)) + 1))
        s, t, lx = _best_letter(cls, cap, u, xs)
        if s >= MIN_LETTER:
            x0 = lx + off
            x1 = x0 + round(max_name_w * u * 1.15) + 4
            out.append(tb.make_row(rgb, cls, t, cap, cap + round(7 * u), lx, x0, x1))
    return out
