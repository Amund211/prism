"""h4_union, then the I3 sandwich stage on the same parse."""

from h4_union import fast_union4
from i3_sandwich import stage


def read_teams(rgb, known):
    out, _, tab, prows = fast_union4(rgb, known)
    if tab is None:
        return out
    return stage(rgb, known, out, tab, prows)
