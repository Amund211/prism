"""h5_cascade_ms, then the I3 sandwich stage."""

import h5_cascade_ms
from i3_sandwich import stage


def read_teams(rgb, known):
    return stage(rgb, known, h5_cascade_ms.read_teams(rgb, known))
