"""h5_cascade_ms, then the I3 layer stage (no-letter lines inside a team block)."""

import h5_cascade_ms
from i3_layer import stage


def read_teams(rgb, known):
    return stage(rgb, known, h5_cascade_ms.read_teams(rgb, known))
