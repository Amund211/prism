"""Tab-list reader: front step (front/), then the text model rk4_all and
policy B4. read_tab: the whole list; read_teams: teams of known names.

Needs numpy, scipy, opencv and onnxruntime: import this package lazily.
"""

from prism.overlay.tabcap.reader.read import read_tab, read_teams

__all__ = ["read_tab", "read_teams"]
