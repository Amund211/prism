"""c_sweep.py <module>: cost matrices once, then sweep max_cost x margin.

The module needs costs(rows, known) -> np.ndarray (rows x names)."""

import importlib
import multiprocessing
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor

from bench import outcome
from c_feats import adaptive_max, assign_loo, cached_feats
from common import assign
from data import image, label, train_names

mod = importlib.import_module(sys.argv[1])
ACCEPT = assign_loo if "--loo" in sys.argv else assign
ADA = next((a for a in sys.argv if a.startswith("--ada")), None)
ADA_A, ADA_B = (float(x) for x in ADA[6:].split(",")) if ADA else (0, 0)


def one(n: str):
    lab = label(n)
    rows = cached_feats(n, image)
    known = list(lab["known"])
    if not rows or not known:
        return n, rows, known, None
    return n, rows, known, mod.costs(rows, known)


def main() -> None:
    with ProcessPoolExecutor(3, mp_context=multiprocessing.get_context("fork")) as ex:
        data = list(ex.map(one, train_names()))
    for mc in [float(x) for x in sys.argv[2].split(",")]:
        for mg in [float(x) for x in sys.argv[3].split(",")]:
            c = Counter()
            for n, rows, known, cost in data:
                got = {}
                if cost is not None:
                    lim = adaptive_max(cost, mc, ADA_A, ADA_B) if ADA else mc
                    pairs = ACCEPT(cost, lim, mg)
                    got = {known[j]: rows[i].team for i, j in pairs if rows[i].team}
                for k, v in outcome(label(n), got).items():
                    c[k] += len(v)
            t = c["correct"] + c["wrong"] + c["unknown"]
            bad = c["wrong"] + c["npc"] + c["extra"]
            print(f"max_cost {mc:.2f} margin {mg:.2f} correct {100 * c['correct'] / t:5.1f} bad {bad}")


if __name__ == "__main__":
    main()
