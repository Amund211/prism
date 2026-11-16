"""G2: cost = min over the 3 best-fitting bank fonts."""

from g_match import read


def read_teams(rgb, known):
    return read(rgb, known, top=3)
