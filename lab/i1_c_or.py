"""I1 cascade, letter check: shape OR OCR."""

import i1_layer
from i1_cascade import read_teams

i1_layer.MODE = "or"

__all__ = ["read_teams"]
