"""d_tune.py <module> [-j N] [--only s]: cost matrices once, then sweep accept rules.

The module has costs(rgb, known) -> (teams per row, names, C rows x names).
"""

import argparse
import importlib
import multiprocessing
import os
import pickle
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("D_CACHE", "1")

from bench import outcome  # noqa: E402
from common import assign  # noqa: E402
from data import image, label, train_names  # noqa: E402

OUT = Path(__file__).parent / "results"


def one(args):
    mod, n = args
    m = importlib.import_module(mod)
    lab = label(n)
    rgb = image(n)
    t = time.perf_counter()
    teams, names, C = m.costs(rgb, list(lab["known"]))
    return n, teams, names, C, time.perf_counter() - t


def score(data, max_cost, margin):
    c = w = u = 0
    for n, teams, names, C, _ in data:
        got = {}
        if C is not None and C.size:
            for i, j in assign(C, max_cost, margin):
                if teams[i]:
                    got[names[j]] = teams[i]
        o = outcome(label(n), got)
        c += len(o["correct"])
        u += len(o["unknown"])
        w += len(o["wrong"]) + len(o["npc"]) + len(o["extra"])
    return c, w, u


def main():
    p = argparse.ArgumentParser()
    p.add_argument("mod")
    p.add_argument("-j", type=int, default=3)
    p.add_argument("--only", default="")
    p.add_argument("--reuse", action="store_true", help="sweep the saved matrices")
    a = p.parse_args()
    names = [n for n in train_names() if a.only in n]
    path = OUT / f"tune_{a.mod}.pkl"
    if a.reuse:
        data = pickle.loads(path.read_bytes())
    else:
        with ProcessPoolExecutor(a.j, mp_context=multiprocessing.get_context("fork")) as ex:
            data = list(ex.map(one, [(a.mod, n) for n in names]))
        path.write_bytes(pickle.dumps(data))
    ts = sorted(d[4] for d in data)
    print("ms median", round(1000 * ts[len(ts) // 2]), "p90", round(1000 * ts[int(len(ts) * 0.9)]))
    for mc in (0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.7):
        line = []
        for mg in (0.0, 0.03, 0.06, 0.1, 0.15):
            c, w, u = score(data, mc, mg)
            tot = c + u + max(0, 0)
            line.append(f"{c:5d}/{w:<3d}")
        print(f"max {mc:.2f}: " + "  ".join(line), " (correct/wrong for margin 0, .03, .06, .1, .15)")


if __name__ == "__main__":
    main()
