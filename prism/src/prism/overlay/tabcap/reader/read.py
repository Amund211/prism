"""The reader: front step -> row crops -> model -> policy.

read_tab: the whole list, policy B4 (no known names).
read_teams: U6 union: snap the rows to the known names, then add the read of
each row that did not snap when the model is sure of it.
"""

from collections.abc import Iterable

import numpy as np

from prism.overlay.tabcap.reader import model
from prism.overlay.tabcap.reader.decode import decode, posterior
from prism.overlay.tabcap.reader.front import front, norm_crop, regions_of, valid
from prism.overlay.tabcap.reader.front.guiscale import Array
from prism.overlay.tabcap.reader.policy import RowRead, candidates, policy_b4
from prism.overlay.tabcap.reader.snap import snap
from prism.overlay.tabcap.screenshot import Screenshot, Team

# Min sequence posterior of a row read that did not snap. Train (out-of-fold
# reads): 0 wrong teams, and fewer misread names than 0 (next.md step 3)
TAU = 0.7


def _rows(rgb: Array) -> tuple[list[RowRead], list[Array]]:
    """Row reads and their model logits"""
    _, tab, prows = front(rgb)
    if tab is None:
        return [], []
    k = tab.k
    rows, logits = [], []
    for r in regions_of(rgb, prows, k):
        row = r.prow.row
        lg = model.logits(norm_crop(rgb, row.y, row.x0, row.x1, k))
        rows.append(RowRead(decode(lg), row.col, row.y))
        logits.append(lg)
    return rows, logits


def read_tab(rgb: Array) -> list[tuple[str, Team | None]]:
    """(name, team | None) per player in the tab list; no known names"""
    return policy_b4(_rows(rgb)[0])


def read_teams(image: Screenshot, known: Iterable[str]) -> dict[str, Team]:
    """{name: team}: the known names that snap, plus names that are not
    known (the caller decides what to do with those)"""
    rows, logits = _rows(np.asarray(image.convert("RGB")))
    teamed = [(i, t, n) for i, t, n in candidates(rows) if t]
    names = sorted(set(known))
    out: dict[str, Team] = {}
    used = set()
    for a, j in snap([n for _, _, n in teamed], names):
        out[names[j]] = teamed[a][1]
        used.add(a)
    for a, (i, t, n) in enumerate(teamed):
        if a in used or n in out or not valid(n):
            continue
        if posterior(logits[i]) >= TAU:
            out[n] = t
    return out
