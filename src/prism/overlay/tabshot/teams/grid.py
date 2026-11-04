"""
Approach E: find all tab rows from the grid the sure rows make.

Tab rows have one pitch (9 GUI px) and the team letters are in one column
(Lunar's icon moves some letters right). Rows B finds give the pitch, the
letter column and the letter -> name offset. At every grid place we try
the 8 bold team letters; where one fits, we add a row.
"""

import numpy as np

from prism.overlay.tabshot.teams import soft
from prism.overlay.tabshot.teams.soft import Array, Seg, SoftRow

MIN_LETTER = 0.35  # The place is known from the grid, so a bit looser
MAX_EMPTY = 3  # Stop after this many grid places without a row


def _best_letter(
    cls: Array, cap: int, u: float, xs: list[int]
) -> tuple[float, int, int]:
    """(score, team index, letter x) of the best team letter near xs"""
    h = round(7 * u)
    best = (-1.0, -1, -1)
    x0, x1 = max(0, xs[0]), min(cls.shape[1], xs[-1] + h)
    box = cls[max(0, cap) : cap + h, x0:x1]
    for t in range(len(soft.TEAM_NAMES)):
        m = box == t
        if m.sum() < 0.15 * h * h:
            continue
        # Only try left edges of this color
        colhas = m.any(axis=0)
        edges = [
            x0 + i
            for i in range(len(colhas))
            if colhas[i] and (i == 0 or not colhas[i - 1])
        ]
        for x in edges:
            if not xs[0] <= x <= xs[-1]:
                continue
            seg = Seg(t, x, x + round(7 * u), cap, cap + h)
            s = soft.letter_score(cls, seg)
            if s > best[0]:
                best = (s, t, x)
    return best


def grid_rows(
    rgb: Array, cls: Array, rows: list[SoftRow], max_name_w: float
) -> list[SoftRow]:
    """rows + rows found on the grid, per tab column. max_name_w: GUI px"""
    if not rows:
        return rows
    u = float(np.median([(r.base - r.cap) / 7 for r in rows]))
    columns: list[list[SoftRow]] = []
    for r in sorted(rows, key=lambda r: r.lx):
        # Lunar icons move letters up to ~10 GUI px right
        if columns and r.lx - columns[-1][0].lx <= 20 * u:
            columns[-1].append(r)
        else:
            columns.append([r])
    return [row for col in columns for row in _column_rows(rgb, cls, col, max_name_w)]


def _column_rows(
    rgb: Array, cls: Array, rows: list[SoftRow], max_name_w: float
) -> list[SoftRow]:
    caps = sorted(r.cap for r in rows)
    u = float(np.median([(r.base - r.cap) / 7 for r in rows]))
    pitch = 9 * u
    # Refine the pitch from the gaps between found rows
    steps = [
        (b - a) / round((b - a) / pitch)
        for a, b in zip(caps, caps[1:])
        if b - a > 0.5 * pitch
    ]
    if steps:
        pitch = float(np.median(steps))
    col = min(r.lx for r in rows)
    off = int(np.median([r.x0 - r.lx for r in rows]))
    H, W = cls.shape
    # Letter: at the column, or after a Lunar icon (up to ~10 GUI px)
    xs = list(range(col - 1, min(W, col + round(11 * u)) + 1))

    def row_at(k: int) -> SoftRow | None:
        cap = round(caps[0] + k * pitch)
        s, t, lx = _best_letter(cls, cap, u, xs)
        if s < MIN_LETTER:
            return None
        x0 = lx + off
        x1 = x0 + round(max_name_w * u * 1.15) + 4
        return soft.make_row(rgb, t, cap, cap + round(7 * u), lx, x0, x1)

    have = {round((r.cap - caps[0]) / pitch) for r in rows}
    last = round((caps[-1] - caps[0]) / pitch)
    out = list(rows)
    for direction in (-1, 1):
        k = 0 if direction < 0 else last
        empty = 0
        while empty < MAX_EMPTY:
            k += direction
            if k in have:
                empty = 0
                continue
            cap = round(caps[0] + k * pitch)
            if cap < 0 or cap + 9 * u >= H:
                break
            row = row_at(k)
            if row is None:
                empty += 1
                continue
            empty = 0
            out.append(row)
    # Places between found rows
    for k in range(1, last):
        if k not in have and (row := row_at(k)) is not None:
            out.append(row)
    return out
