"""G1: best bank font per image (width prune to 6, then IoU fit)."""

from g_match import read


def read_teams(rgb, known):
    return read(rgb, known, top=1)
