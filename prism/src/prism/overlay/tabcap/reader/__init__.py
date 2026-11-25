"""Tab-list reader: front step (front/), then the text model rk4_all.
read_tab: the whole list (policy B4); read_teams: teams by name (U6 union:
known names by snap, other names when the model is sure).

Needs numpy, scipy, opencv and onnxruntime: import this package lazily.
"""

from prism.overlay.tabcap.reader.read import read_tab, read_teams

__all__ = ["read_tab", "read_teams"]
