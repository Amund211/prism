"""G3 (speed): width prune to 3 fonts, cost = min over them."""

from g_match import read


def read_teams(rgb, known):
    return read(rgb, known, top=3, prune=3)
