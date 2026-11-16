"""H4b: H4, then E2c row bands (RapidOCR) only, on rows g2 did not claim,
matched only against names still without a team. No E2 name crops."""

import numpy as np

import e2c_rowband as rb
from e2d_union import combine
from h4_union import fast_union4


def bands(rgb: np.ndarray, tab) -> list[tuple[int, int, int, int]]:
    """e2c_rowband.bands on a given tab (no second find_tab)"""
    if tab is None or not tab.rows:
        return []
    k = tab.k
    p = 9 * k
    out = []
    cols: dict[int, list] = {}
    for r in tab.rows:
        cols.setdefault(r.col, []).append(r)
    for rs in cols.values():
        x0 = min(r.x0 for r in rs) - 4 * k
        x1 = max(r.x1 for r in rs) + 2 * k
        base = rs[0].y
        idx = sorted({round((r.y - base) / p) for r in rs})
        for i in range(idx[0] - 1, idx[-1] + 2):
            y = base + i * p
            if 0 <= y and y + 8 * k <= rgb.shape[0]:
                out.append((y, max(0, x0), min(rgb.shape[1], x1), k))
    return out


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    out, g, tab, prows = fast_union4(rgb, known)
    left = [n for n in known if n not in out]
    if not left or tab is None:
        return out
    claimed = [p for n, (_, p) in g.items() if n in out]

    def free(y: int, x0: int, x1: int, k: int) -> bool:
        return not any(abs(p.row.y - y) <= 2 * k and x0 <= p.row.x0 <= x1 for p in claimed)

    lines = []
    for y, x0, x1, k in bands(rgb, tab):
        if not free(y, x0, x1, k):
            continue
        t = rb.ocr_band(rgb, y, x0, x1, k)
        if t.strip():
            lines.append((t, rb.text_team(rgb, y, x0, x1, k)))
    c = rb.match_all([t for t, _ in lines], [c for _, c in lines], left) if lines else {}
    out.update(combine({}, c))
    return out
