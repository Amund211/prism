"""I2 cascade, tight, letter veto: only a clearly different letter rejects."""

import i2_spot
from i2_cascade import read_teams

i2_spot.DX = 6
i2_spot.MAX_COST = 0.35
i2_spot.LET_VETO = True

__all__ = ["read_teams"]
