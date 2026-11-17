"""J3: j2_bg (cell grid, shadow mask, h4 vote), with the ping anchor as the
second finder (Lunar draws no cells), then the old find_tab.

J3_STAGES  which finders to try, in order: g (cell grid), p (ping), f (find_tab)
"""
import os

os.environ.setdefault("J_MASK", "shadow")

import numpy as np  # noqa: E402

import grid3  # noqa: E402
import ping_grid  # noqa: E402
from j2_bg import tab_from_grid, union  # noqa: E402
from rows import find_tab  # noqa: E402

STAGES = os.environ.get("J3_STAGES", "gpf")


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    out = {}
    for s in STAGES:
        if s == "g":
            tab, bm = tab_from_grid(rgb, grid3.find_grid(rgb))
        elif s == "p":
            tab, bm = tab_from_grid(rgb, ping_grid.find_ping(rgb))
        else:
            tab, bm = find_tab(rgb), None
        if tab is None:
            continue
        out, prows = union(rgb, known, tab, bm)
        if sum(1 for p in prows if p.team) >= 2:
            return out
    return out
