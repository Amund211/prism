"""G2 without the image's own font family in the bank."""

from g_match import read_loo


def read_teams(rgb, known):
    return read_loo(rgb, known, top=3)
