"""H4: H1 vote, but one common.parse feeds g2, d3 and c5."""

import numpy as np
from rapidfuzz.distance import Levenshtein
from rapidfuzz.process import cdist

import c5_fast
import d3_classify
from c_feats import RowF, row_feats
from d1_calib import finish
from d_core import Ext, Font, XRow, _calib_glyphs, _calib_lines, split_word, to_font_px
from common import parse
from h_common import g2_rows, vote


def d3_on(rgb, tab, prows, known) -> dict[str, str]:
    """d3_classify.read_teams on a given parse (d_core.extract without its own parse)"""
    names = sorted(set(known))
    k = tab.k
    rows, seen = [], set()
    for p in prows:
        if p.name is None or (p.row.y, p.name.x0) in seen:
            continue
        seen.add((p.row.y, p.name.x0))
        gl, gaps = split_word(p.name, k)
        rows.append(XRow(p.team, gl, gaps, to_font_px(p.name.mask, k)))
    if not rows or not names:
        return {}
    ext = Ext(k, rows, _calib_glyphs(_calib_lines(rgb, tab, prows), k))
    f = Font()
    for c, g in ext.calib:
        f.add(c, g)
    read = d3_classify._read(ext, f, names)
    C = np.asarray(cdist(read, names, scorer=Levenshtein.normalized_distance), float)
    return finish(ext, names, C, d3_classify.MAX_COST, d3_classify.MARGIN)


def c5_on(tab, prows, known) -> dict[str, str]:
    """c5_fast.read_teams on a given parse (c_feats.feats without its own parse)"""
    out: list[RowF] = []
    seen = set()
    for p in prows:
        f = row_feats(p, tab.k)
        if f is None or (f.y, f.x0) in seen:
            continue
        seen.add((f.y, f.x0))
        out.append(f)
    return c5_fast.match(out, known)


def fast_union4(rgb: np.ndarray, known: list[str]):
    """(teams, g2 hits with prow, tab, prows)"""
    tab, prows = parse(rgb)
    if tab is None or not known:
        return {}, {}, tab, prows
    g = g2_rows(rgb, known, tab, prows)
    res = [{n: t for n, (t, _) in g.items()}, d3_on(rgb, tab, prows, known), c5_on(tab, prows, known)]
    return vote(res), g, tab, prows


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    return fast_union4(rgb, known)[0]
