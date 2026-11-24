"""J3 matcher: j3_grid front rows + the g2 / d3 / c5 known-name vote.
The front part (grid_parse, slot_team, hue_team) is in j3_grid.py."""

import numpy as np

from common import parse
from h4_union import c5_on, d3_on
from h_common import g2_rows, vote
from j3_grid import HUES, SLOT, grid_parse, hue_team, slot_team  # noqa: F401  (re-export for lab callers)
from rows import find_tab


def match(rgb, known, tab, prows):
    g = g2_rows(rgb, known, tab, prows)
    res = [{n: t for n, (t, _) in g.items()}, d3_on(rgb, tab, prows, known), c5_on(tab, prows, known)]
    return vote(res), g


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    if not known:
        return {}
    _, tab, prows = grid_parse(rgb)
    if tab is not None and sum(1 for p in prows if p.team) >= 2:
        return match(rgb, known, tab, prows)[0]
    tab, prows = parse(rgb, find_tab(rgb))
    return match(rgb, known, tab, prows)[0] if tab is not None else {}
