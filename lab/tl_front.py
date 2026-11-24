"""Tab-list (open set) shared front: rows from the j4 finder chain, name
validity, row dedupe. No known names are used here."""

import re

import numpy as np

import ping_grid
from common import parse
from j3_grid import grid_parse
from lunar_mask import lunar_mask
from rows import find_tab

NAME_RE = re.compile(r"^[A-Za-z0-9_]{3,16}$")


def front(rgb: np.ndarray):
    """(finder, tab, prows): j4_slotping order, first finder with >= 2 team rows"""
    _, tab, prows = grid_parse(rgb)
    if tab is not None and sum(1 for p in prows if p.team) >= 2:
        return "grid", tab, prows
    g = ping_grid.find_ping(rgb)
    if g is not None:
        _, tab, prows = grid_parse(rgb, g=g, maskfn=lunar_mask, icon=True)
        if tab is not None and sum(1 for p in prows if p.team) >= 2:
            return "ping", tab, prows
    tab, prows = parse(rgb, find_tab(rgb))
    return "old", tab, prows


def clean(t: str) -> str:
    t = re.sub(r"^\[[^\]]*\]\s*", "", t.strip())
    return t.replace(" ", "")


def valid(name: str) -> bool:
    return bool(NAME_RE.match(name))
