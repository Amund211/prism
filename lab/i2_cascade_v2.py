"""I2 cascade, tight, letter veto; a hit with no clear letter needs cost <= 0.2."""

import i2_spot
from i2_cascade import read_teams

i2_spot.DX = 6
i2_spot.MAX_COST = 0.35
i2_spot.LET_VETO = True
i2_spot.VETO_COST = 0.2

__all__ = ["read_teams"]
