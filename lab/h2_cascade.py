"""H2: H1, then RapidOCR (E2 name crops) only on rows g2 did not claim,
matched only against names still without a team."""

import numpy as np

from e2_rapidocr import MARGIN, MAX_COST, ocr
from e_ocrcommon import candidates, match, name_crop
from h_common import fast_union


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    out, g, tab, prows = fast_union(rgb, known)
    left = [n for n in known if n not in out]
    if not left or tab is None:
        return out
    used = {id(p) for n, (_, p) in g.items() if n in out}
    cand = [p for p in candidates(prows) if id(p) not in used and p.team]
    if not cand:
        return out
    texts = [ocr(name_crop(p, 5, pad=8)) for p in cand]
    got = match(texts, [p.team for p in cand], left, MAX_COST, MARGIN)
    out.update(got)
    return out
