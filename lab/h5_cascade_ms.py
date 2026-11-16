"""H5 cascade with more OCR passes (scales 5, 3, 8) on segments that read badly."""

import h5_layer
from h5_cascade import read_teams

h5_layer.SCALES = (5, 3, 8)

__all__ = ["read_teams"]
