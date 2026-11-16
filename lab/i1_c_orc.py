"""I1 cascade, letter check: (shape OR OCR) AND letter colour == name colour."""

import i1_layer
from i1_cascade import read_teams

i1_layer.MODE = "or_c"

__all__ = ["read_teams"]
