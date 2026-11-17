"""J4: j3_slot (cell grid + letter slot), then the ping anchor (Lunar, no
cells; letter slot on lunar_mask, retried after a client icon), then the
old find_tab.

J4_PING_SLOT 0: no letter slot on ping rows
"""

import os

import numpy as np

from lunar_mask import lunar_mask

PING_SLOT = os.environ.get("J4_PING_SLOT", "1") == "1"

import ping_grid
from common import parse
from j3_slot import grid_parse, match
from rows import find_tab


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    if not known:
        return {}
    for g in (None, "ping"):
        if g == "ping":
            g = ping_grid.find_ping(rgb)
            if g is None:
                continue
            _, tab, prows = grid_parse(rgb, slot=PING_SLOT, g=g, maskfn=lunar_mask, icon=True)
        else:
            _, tab, prows = grid_parse(rgb)
        if tab is not None and sum(1 for p in prows if p.team) >= 2:
            return match(rgb, known, tab, prows)[0]
    tab, prows = parse(rgb, find_tab(rgb))
    return match(rgb, known, tab, prows)[0] if tab is not None else {}
