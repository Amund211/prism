"""The reader: front step -> row crops -> model -> policy B4 (-> snap)."""

from collections.abc import Iterable

import numpy as np

from prism.overlay.tabcap.reader import model
from prism.overlay.tabcap.reader.front import front, norm_crop, regions_of
from prism.overlay.tabcap.reader.front.guiscale import Array
from prism.overlay.tabcap.reader.policy import RowRead, policy_b4
from prism.overlay.tabcap.reader.snap import snap
from prism.overlay.tabcap.screenshot import Screenshot, Team


def read_tab(rgb: Array) -> list[tuple[str, Team | None]]:
    """(name, team | None) per player in the tab list; no known names"""
    _, tab, prows = front(rgb)
    if tab is None:
        return []
    k = tab.k
    rows = []
    for r in regions_of(rgb, prows, k):
        row = r.prow.row
        crop = norm_crop(rgb, row.y, row.x0, row.x1, k)
        rows.append(RowRead(model.read(crop), row.col, row.y))
    return policy_b4(rows)


def read_teams(image: Screenshot, known: Iterable[str]) -> dict[str, Team]:
    """{name: team} for the known names whose team we could read"""
    names = sorted(set(known))
    if not names:
        return {}
    return snap(read_tab(np.asarray(image.convert("RGB"))), names)
