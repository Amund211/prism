"""I3: tab-list structure stage. Train data: rows are sorted by team
(TEAM_ORDER) and each team is one contiguous block (183/183 images).
So a row without a letter between two rows of team T is team T.

stage(): g2 cost (all known names x all name regions, teamless rows too),
Hungarian + margin; a still-unknown name matched to a teamless row gets
the sandwich team.
"""

import numpy as np

from common import assign, parse
from g_bank import bank
from g_match import cost_matrix, regions_of, width_scores

MAX_COST = 0.4
MARGIN = 0.12


def sandwich(prows: list) -> dict[int, str]:
    """id(prow) -> team for teamless rows between two rows of one team"""
    out: dict[int, str] = {}
    bycol: dict[int, list] = {}
    for p in prows:
        bycol.setdefault(p.row.col, []).append(p)
    for ps in bycol.values():
        ps.sort(key=lambda p: p.row.y)
        teams = [p.team for p in ps]
        for i, p in enumerate(ps):
            if p.team is not None:
                continue
            up = next((t for t in reversed(teams[:i]) if t), None)
            dn = next((t for t in teams[i + 1:] if t), None)
            if up and up == dn:
                out[id(p)] = up
    return out


def g2_cost(rgb, known, tab, prows, top: int = 3, prune: int = 6):
    k = tab.k
    regions = regions_of(rgb, prows, k)
    if not regions:
        return [], None
    fonts = list(bank())
    ws = width_scores(regions, known, fonts, k)
    cand = [fonts[i] for i in np.argsort(ws)[:prune]]
    costs = [cost_matrix(regions, known, f, k) for f in cand]
    fit = [np.sort(c.min(axis=1))[: max(3, len(regions) // 2)].mean() for c in costs]
    return regions, np.min([costs[i] for i in np.argsort(fit)[:top]], axis=0)


def stage(rgb, known: list[str], out: dict[str, str], tab=None, prows=None,
          max_cost: float = MAX_COST, margin: float = MARGIN) -> dict[str, str]:
    out = dict(out)
    if not known or all(n in out for n in known):
        return out
    if tab is None:
        tab, prows = parse(rgb)
    if tab is None:
        return out
    sw = sandwich(prows)
    if not sw:
        return out
    regions, cost = g2_cost(rgb, known, tab, prows)
    if cost is None:
        return out
    for i, j in assign(cost, max_cost=max_cost, margin=margin):
        n = known[j]
        p = regions[i].prow
        if n not in out and p.team is None and id(p) in sw:
            out[n] = sw[id(p)]
    return out
