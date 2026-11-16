"""I4 band: CRNN on parsed name regions, then CRNN on whole row bands
(e2c bands, incl. rows the parse missed) for names still unknown; band
reads matched like e2c (letter / colour team). No RapidOCR."""

import os

import numpy as np

import e2c_rowband as rb
from common import assign, parse
from g_match import regions_of
from i4_rec import MARGIN, MAX_COST, cost, loo_model, read_crops
from i4_synth import norm_crop

LOO = bool(os.environ.get("I4_LOO"))


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    tab, prows = parse(rgb)
    if tab is None or not known:
        return {}
    k = tab.k
    model = loo_model(rgb, tab, prows, known) if LOO else "full"
    regions = regions_of(rgb, prows, k)
    out, claimed = {}, []
    if regions:
        texts = read_crops([norm_crop(rgb, r.prow.row.y, r.x0, r.x1, k) for r in regions], model)
        C = np.array([[cost(t, n) for n in known] for t in texts])
        for i, j in assign(C, MAX_COST, MARGIN):
            claimed.append(regions[i].prow.row)
            if regions[i].prow.team:
                out[known[j]] = regions[i].prow.team
    left = [n for n in known if n not in out]
    if not left:
        return out
    bs = [b for b in rb.bands(rgb)
          if not any(abs(r.y - b[0]) <= 2 * b[3] and b[1] <= r.x0 <= b[2] for r in claimed)]
    if not bs:
        return out
    texts = read_crops([norm_crop(rgb, y, x0, x1, kk) for y, x0, x1, kk in bs], model)
    lines = [(t, rb.text_team(rgb, *b)) for t, b in zip(texts, bs) if t.strip()]
    if lines:
        got = rb.match_lines([t for t, _ in lines], [c for _, c in lines], left)
        for n, team in got.items():
            # strict: the read letter must name the same team as the colour
            i = max(range(len(lines)), key=lambda i: rb.score(n, lines[i][0])[0])
            letter = rb.score(n, lines[i][0])[1]
            if STRICT and (letter in (None, "?") or letter != lines[i][1]):
                continue
            out[n] = team
    return out


STRICT = True
