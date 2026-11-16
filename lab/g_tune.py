"""g_tune.py dump|sweep [top] [loo]: dump cost matrices for train, then sweep
the accept rule offline (max_cost, margin) and print correct / wrong."""

import multiprocessing
import pickle
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from bench import outcome
from common import assign, parse
from data import image, label, train_names
from g_bank import bank, excluded_for
from g_match import cost_matrix, regions_of, width_scores

OUT = Path(__file__).parent / "results"


def dump_one(args: tuple[str, int, bool]) -> tuple[str, dict]:
    n, top, loo = args
    lab = label(n)
    rgb = image(n)
    known = list(lab["known"])
    tab, prows = parse(rgb)
    if tab is None or not known:
        return n, {"cost": None}
    k = tab.k
    regions = regions_of(rgb, prows, k)
    if not regions:
        return n, {"cost": None}
    ex = excluded_for(lab["setup"]["font"]) if loo else set()
    if ex is None:
        fonts0 = [f for f in bank() if f.fid != "vanilla"]
        best = fonts0[int(np.argmin(width_scores(regions, known, fonts0, k)))]
        ex = {f.fid for f in fonts0 if f.family == best.family}
    fonts = [f for f in bank() if f.fid not in ex]
    ws = width_scores(regions, known, fonts, k)
    cand = [fonts[i] for i in np.argsort(ws)[:6]]
    costs = [cost_matrix(regions, known, f, k) for f in cand]
    fit = [np.sort(c.min(axis=1))[: max(3, len(regions) // 2)].mean() for c in costs]
    order = np.argsort(fit)[:top]
    cost = np.min([costs[i] for i in order], axis=0)
    return n, {"cost": cost, "teams": [r.prow.team for r in regions], "known": known}


def main() -> None:
    mode = sys.argv[1]
    top = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    loo = len(sys.argv) > 3
    path = OUT / f"g_tune_top{top}{'_loo' if loo else ''}.pkl"
    if mode == "dump":
        with ProcessPoolExecutor(3, mp_context=multiprocessing.get_context("fork")) as ex:
            res = dict(ex.map(dump_one, [(n, top, loo) for n in train_names()]))
        path.write_bytes(pickle.dumps(res))
        return
    res = pickle.loads(path.read_bytes())
    labels = {n: label(n) for n in res}
    for mc in (0.2, 0.25, 0.3, 0.35, 0.4, 0.45):
        for mg in (0.03, 0.06, 0.09, 0.12, 0.18):
            c = w = tot = 0
            for n, d in res.items():
                got = {}
                if d["cost"] is not None:
                    for i, j in assign(d["cost"], mc, mg):
                        if d["teams"][i]:
                            got[d["known"][j]] = d["teams"][i]
                o = outcome(labels[n], got)
                c += len(o["correct"])
                w += len(o["wrong"]) + len(o["npc"]) + len(o["extra"])
                tot += len(o["correct"]) + len(o["wrong"]) + len(o["unknown"])
            print(f"max_cost {mc:.2f} margin {mg:.2f}  correct {100 * c / tot:5.1f}  wrong {w:3d} ({100 * w / tot:.2f} %)")


if __name__ == "__main__":
    main()
