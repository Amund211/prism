"""Shared bits for the H (chain) variants."""

import numpy as np

import c5_fast
import d3_classify
from common import assign, parse
from g_bank import bank
from g_match import cost_matrix, regions_of, width_scores


def g2_rows(rgb: np.ndarray, known: list[str], tab, prows, top: int = 3, prune: int = 6,
            max_cost: float = 0.4, margin: float = 0.12) -> dict[str, tuple[str, object]]:
    """g_match.read(top=3) on a given parse: {name: (team, prow)}"""
    if tab is None or not known:
        return {}
    k = tab.k
    regions = regions_of(rgb, prows, k)
    if not regions:
        return {}
    fonts = list(bank())
    ws = width_scores(regions, known, fonts, k)
    cand = [fonts[i] for i in np.argsort(ws)[:prune]]
    costs = [cost_matrix(regions, known, f, k) for f in cand]
    fit = [np.sort(c.min(axis=1))[: max(3, len(regions) // 2)].mean() for c in costs]
    cost = np.min([costs[i] for i in np.argsort(fit)[:top]], axis=0)
    out = {}
    for i, j in assign(cost, max_cost=max_cost, margin=margin):
        t = regions[i].prow.team
        if t:
            out[known[j]] = (t, regions[i].prow)
    return out


def vote(results: list[dict[str, str]]) -> dict[str, str]:
    """Team if all methods that answer agree"""
    out: dict[str, str] = {}
    bad: set[str] = set()
    for r in results:
        for n, t in r.items():
            if n in bad:
                continue
            if n in out and out[n] != t:
                del out[n]
                bad.add(n)
            else:
                out[n] = t
    return out


def fast_union(rgb: np.ndarray, known: list[str]):
    """(teams, g2 hits with prow, tab, prows)"""
    tab, prows = parse(rgb)
    g = g2_rows(rgb, known, tab, prows)
    res = [
        {n: t for n, (t, _) in g.items()},
        d3_classify.read_teams(rgb, known),
        c5_fast.read_teams(rgb, known),
    ]
    return vote(res), g, tab, prows
