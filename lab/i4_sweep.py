"""I4 sweep (train only): Levenshtein vs CTC cost, max_cost x margin.
i4_sweep.py MODEL [loo]"""

import multiprocessing
import sys
from collections import Counter

import numpy as np

from bench import outcome
from common import assign, parse
from data import image, label, train_names
from g_match import regions_of
from i4_rec import cost, ctc_cost, decode, logits, loo_model
from i4_synth import norm_crop

MODEL = sys.argv[1]
LOO = len(sys.argv) > 2
GRID = [(mc, mg) for mc in (0.25, 0.3, 0.34, 0.4, 0.45, 0.5) for mg in (0.08, 0.12, 0.18)]
SCALES = (1.0, 2.0, 4.0)


def one(name: str):
    lab = label(name)
    known = list(lab["known"])
    rgb = image(name)
    tab, prows = parse(rgb)
    res = {}
    if tab is None or not known:
        regions = []
    else:
        regions = regions_of(rgb, prows, tab.k)
    if regions:
        m = loo_model(rgb, tab, prows, known) if LOO else MODEL
        lps = logits([norm_crop(rgb, r.prow.row.y, r.x0, r.x1, tab.k) for r in regions], m)
        costs = {"lev": np.array([[cost(decode(lp), n) for n in known] for lp in lps])}
        for s in SCALES:
            costs[f"ctc{s}"] = np.array([ctc_cost(lp, known, s) for lp in lps])
    for kind in ["lev"] + [f"ctc{s}" for s in SCALES]:
        for mc, mg in GRID:
            got = {}
            if regions:
                for i, j in assign(costs[kind], mc, mg):
                    if regions[i].prow.team:
                        got[known[j]] = regions[i].prow.team
            o = outcome(lab, got)
            res[(kind, mc, mg)] = (len(o["correct"]), len(o["wrong"]) + len(o["npc"]) + len(o["extra"]),
                                   len(o["correct"]) + len(o["wrong"]) + len(o["unknown"]))
    return res


def main() -> None:
    with multiprocessing.get_context("fork").Pool(2) as p:
        parts = p.map(one, train_names())
    tot = Counter()
    for r in parts:
        for key, (c, w, n) in r.items():
            tot[key + ("c",)] += c
            tot[key + ("w",)] += w
            tot[key + ("n",)] += n
    rows = sorted({k[:3] for k in tot})
    for key in rows:
        n = tot[key + ("n",)]
        print(f"{key[0]:8s} mc {key[1]:.2f} mg {key[2]:.2f}  correct {100 * tot[key + ('c',)] / n:5.1f}  wrong {tot[key + ('w',)]}")


if __name__ == "__main__":
    main()
