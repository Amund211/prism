"""The front step: tab rows from the finder chain, name validity, clean-up.
No known names are used here."""

import re

from prism.overlay.tabcap.reader.front import ping
from prism.overlay.tabcap.reader.front.guiscale import Array
from prism.overlay.tabcap.reader.front.lunar_mask import lunar_mask
from prism.overlay.tabcap.reader.front.parse import PRow, parse
from prism.overlay.tabcap.reader.front.rows import Tab, find_tab
from prism.overlay.tabcap.reader.front.slot import grid_parse
from prism.overlay.tabcap.reader.front.textmask import Shadow

NAME_RE = re.compile(r"^[A-Za-z0-9_]{3,16}$")


def front(rgb: Array) -> tuple[str, Tab | None, list[PRow]]:
    """(finder, tab, prows): the first finder (grid, ping, old) whose parse
    gives >= 2 rows with a team"""
    sh = Shadow(rgb)
    _, tab, prows = grid_parse(rgb, sh=sh)
    if tab is not None and sum(1 for p in prows if p.team) >= 2:
        return "grid", tab, prows
    g = ping.find_ping(rgb)
    if g is not None:
        _, tab, prows = grid_parse(rgb, g=g, maskfn=lunar_mask, icon=True, sh=sh)
        if tab is not None and sum(1 for p in prows if p.team) >= 2:
            return "ping", tab, prows
    tab, prows = parse(rgb, find_tab(rgb, sh=sh))
    return "old", tab, prows


def clean(t: str) -> str:
    t = re.sub(r"^\[[^\]]*\]\s*", "", t.strip())
    return t.replace(" ", "")


def valid(name: str) -> bool:
    return bool(NAME_RE.match(name))
