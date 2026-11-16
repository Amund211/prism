"""I2 cascade, tight: hits within 6 font px are one word; max cost 0.35."""

import i2_spot
from i2_cascade import read_teams

i2_spot.DX = 6
i2_spot.MAX_COST = 0.35

__all__ = ["read_teams"]
