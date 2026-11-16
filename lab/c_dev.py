"""c_dev.py <module> [--only s] [--show]: fast dev bench on cached row features.

Same scoring as bench.py; no timing (use bench.py for that).
"""

import argparse
import importlib
import json
import multiprocessing
from collections import Counter
from concurrent.futures import ProcessPoolExecutor

from bench import outcome
from c_feats import cached_feats
from data import image, label, train_names


def prep(n: str) -> str:
    cached_feats(n, image)
    return n


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("algo")
    p.add_argument("--only", default="")
    p.add_argument("--show", action="store_true")
    p.add_argument("--groups", action="store_true")
    a = p.parse_args()
    names = [n for n in train_names() if a.only in n]
    with ProcessPoolExecutor(3, mp_context=multiprocessing.get_context("fork")) as ex:
        list(ex.map(prep, names))
    mod = importlib.import_module(a.algo)
    c = Counter()
    by: dict[str, Counter] = {}
    for n in names:
        lab = label(n)
        got = mod.match(cached_feats(n, image), list(lab["known"]))
        o = outcome(lab, got)
        f = lab["setup"]["font"] or "none"
        g = by.setdefault(f, Counter())
        for k, v in o.items():
            c[k] += len(v)
            g[k] += len(v)
        if a.show and (o["wrong"] or o["npc"] or o["extra"]):
            print(n, json.dumps({k: o[k] for k in ("wrong", "npc", "extra") if o[k]}))
    if a.groups:
        for f, g in sorted(by.items()):
            t = max(1, g["correct"] + g["wrong"] + g["unknown"])
            print(f"  {f:34s} ok {100 * g['correct'] / t:5.1f} bad {g['wrong'] + g['npc'] + g['extra']}")
    t = c["correct"] + c["wrong"] + c["unknown"]
    bad = c["wrong"] + c["npc"] + c["extra"]
    print(f"{a.algo} correct {100 * c['correct'] / t:.1f} wrong {100 * bad / t:.2f} ({bad}) unknown {100 * c['unknown'] / t:.1f} rows {t}")


if __name__ == "__main__":
    main()
