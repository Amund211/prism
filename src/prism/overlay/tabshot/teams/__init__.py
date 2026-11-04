"""
Read Bedwars teams from one screenshot of the tab list.

A pure function: one image and the known names in, {name: team} out. No
state between screenshots. Pipeline (see the prototype plan, "AE"):
1. `exact`: exact glyph cipher. Sure, but needs exact pixels.
2. `learn` + `grid`: blur-tolerant rows, generic font, font learned from
   this image. A's teams are fixed.

Needs numpy, scipy and Pillow: import this package lazily.
"""

from collections.abc import Iterable

import numpy as np

from prism.overlay.tabshot.screenshot import Screenshot, Team
from prism.overlay.tabshot.teams import exact, learn


def read_teams(image: Screenshot, known: Iterable[str]) -> dict[str, Team]:
    """{name: team} for the known names whose team we could read"""
    names = sorted(set(known))
    if not names:
        return {}
    rgb = np.asarray(image.convert("RGB"))
    sure = exact.read_teams(rgb, names)
    return {**learn.read_teams(rgb, names, fixed=sure), **sure}
