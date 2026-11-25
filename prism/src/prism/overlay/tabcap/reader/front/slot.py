"""Rows from a cell grid (grid or ping finder), parse, and the team from the
grid letter slot.

The grid gives the cell x0, so the team letter is the first glyph at x0 + 9k,
before the name word. A row with no team from find_letter gets one when the
slot left of the name has a full-height glyph in the letter mask.
Team = colour of the name, else of the brightest slot pixels.
"""

from collections.abc import Callable

import numpy as np

from prism.overlay.tabcap.reader.front import grid
from prism.overlay.tabcap.reader.front.bgmask import bg_mask
from prism.overlay.tabcap.reader.front.guiscale import Array
from prism.overlay.tabcap.reader.front.parse import PRow, parse, team_of
from prism.overlay.tabcap.reader.front.rowparse import nearest_team
from prism.overlay.tabcap.reader.front.rows import Row, Tab, runs_of
from prism.overlay.tabcap.reader.front.textmask import Shadow

SLOT = True

HUES = {"red": 0, "yellow": 60, "green": 120, "aqua": 180, "blue": 240, "pink": 300}

MaskFn = Callable[[Array, grid.Grid], Array]


def hue_team(c: Array) -> str | None:
    """Team by hue, so dimmed (overlay) and remapped (packs) colours still
    match; gray / white differ only in brightness, so they need a close match"""
    c = np.asarray(c, float)
    hi, lo = c.max(), c.min()
    if hi < 40:
        return None
    if (hi - lo) / hi < 0.4:
        return nearest_team(tuple(c), max_dist=60)
    r, g, b = c
    if hi == r:
        h = 60 * ((g - b) / (hi - lo)) % 360
    elif hi == g:
        h = 60 * ((b - r) / (hi - lo) + 2)
    else:
        h = 60 * ((r - g) / (hi - lo) + 4)
    best = min(HUES, key=lambda t: min(abs(h - HUES[t]), 360 - abs(h - HUES[t])))
    d = min(abs(h - HUES[best]), 360 - abs(h - HUES[best]))
    return best if d <= 20 else None


def slot_team(
    rgb: Array, bm: Array, p: PRow, x_text: int, k: int
) -> tuple[str | None, str]:
    """(team, why) from the glyph between x_text and the name word"""
    assert p.name is not None
    y, name = p.row.y, p.name
    a = x_text
    m = bm[y : y + 8 * k, a : name.x1]
    spans = runs_of(m.any(axis=0))
    if len(spans) < 3:
        return None, "empty"
    # letter = first glyph at the text start (the parse can join it to the
    # name word); parts closer than k + 1 join
    p0, q = spans[0]
    j = 0
    while j + 1 < len(spans) and spans[j + 1][0] - q < k + 1:
        j += 1
        q = spans[j][1]
    if p0 > 4 * k:
        return None, "far"
    g = m[:, p0:q]
    on = np.flatnonzero(g.any(axis=1))
    if (
        not (2 * k <= q - p0 <= 8 * k)
        or on[-1] - on[0] < 4 * k - 1
        or g.sum() < 4 * k * k
    ):
        return None, "shape"
    # a space follows the letter: wider than the gaps inside the name
    rest = spans[j + 1 :]
    inner = [b0 - a1 for (_, a1), (b0, _) in zip(rest, rest[1:])]
    med = float(np.median(inner)) if inner else k
    if len(rest) < 2 or rest[0][0] - q < max(3 * k, 2 * med):
        return None, "gap"
    t = team_of(name)
    if t is None:
        px = rgb[y : y + 8 * k, a + p0 : a + q][g].astype(np.float32)
        hi = px.max(axis=1) >= np.quantile(px.max(axis=1), 0.75)
        t = hue_team(np.median(px[hi], axis=0))
    return t, "ok" if t else "colour"


def grid_parse(
    rgb: Array,
    slot: bool = SLOT,
    g: grid.Grid | None = None,
    maskfn: MaskFn = bg_mask,
    icon: bool = False,
    sh: Shadow | None = None,
) -> tuple[grid.Grid | None, Tab | None, list[PRow]]:
    """g: a Grid from another finder. maskfn: letter mask (bg_mask needs row
    cells; ping rows use lunar_mask). icon: when the slot fails, try again
    after a client icon (8k + 1k gap; Lunar moon). sh: shared shadow masks"""
    if g is None:
        g = grid.find_grid(rgb)
    if g is None:
        return None, None, []
    k = g.k
    mask = (Shadow(rgb) if sh is None else sh).mask(k)
    rows = []
    for col, (x0, x1) in enumerate(g.cols):
        lo, hi = x0 + 9 * k, x1 - 11 * k
        for y in g.tops:
            spans = [
                (lo + p, lo + q)
                for p, q in runs_of(mask[y : y + 8 * k, lo:hi].any(axis=0))
            ]
            if spans:
                rows.append(Row(y, spans[0][0], spans[-1][1], k, col, spans))
    if not rows:
        return g, None, []
    tab, prows = parse(rgb, Tab(k, rows, mask, len(rows)))
    # weak grid = under a translucent overlay: blended colours look like gray
    if slot and not g.weak:
        bm = maskfn(rgb, g)
        for p in prows:
            if p.team is None and p.name is not None:
                xt = g.cols[p.row.col][0] + 9 * k
                p.team, why = slot_team(rgb, bm, p, xt, k)
                if (
                    icon
                    and p.team is None
                    and why in ("shape", "gap")
                    and xt + 9 * k < p.name.x1
                ):
                    p.team, _ = slot_team(rgb, bm, p, xt + 9 * k, k)
    return g, tab, prows
