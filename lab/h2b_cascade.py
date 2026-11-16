"""H2b: H1, then E2 crops + E2c row bands (RapidOCR), only on rows g2 did not
claim, matched only against names still without a team (E2d combine)."""

import numpy as np

import e2c_rowband as rb
from e2_rapidocr import MARGIN, MAX_COST, ocr
from e2d_union import combine
from e_ocrcommon import candidates, match, name_crop
from h_common import fast_union


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    out, g, tab, prows = fast_union(rgb, known)
    left = [n for n in known if n not in out]
    if not left or tab is None:
        return out
    claimed = [p for n, (_, p) in g.items() if n in out]
    used = {id(p) for p in claimed}
    cand = [p for p in candidates(prows) if id(p) not in used and p.team]
    texts = [ocr(name_crop(p, 5, pad=8)) for p in cand]
    a = match(texts, [p.team for p in cand], left, MAX_COST, MARGIN)

    def free(y: int, x0: int, x1: int, k: int) -> bool:
        return not any(abs(p.row.y - y) <= 2 * k and x0 <= p.row.x0 <= x1 for p in claimed)

    lines = []
    for y, x0, x1, k in rb.bands(rgb):
        if not free(y, x0, x1, k):
            continue
        t = rb.ocr_band(rgb, y, x0, x1, k)
        if t.strip():
            lines.append((t, rb.text_team(rgb, y, x0, x1, k)))
    c = rb.match_all([t for t, _ in lines], [c for _, c in lines], left) if lines else {}
    out.update(combine(a, c))
    return out
