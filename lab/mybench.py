"""mybench.py <module in scratchpad> [-j N] [--only s] [--ref result.json]
Same scoring as lab/bench.py; writes results to the scratchpad only."""
import argparse
import json
import multiprocessing
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).parent
LAB = HERE
sys.path.insert(0, str(LAB))
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import bench  # noqa: E402
from data import label, train_names  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("algo")
    p.add_argument("-j", type=int, default=3)
    p.add_argument("--only", default="")
    p.add_argument("--ref", default="h4_union")
    p.add_argument("--tag", default="")
    a = p.parse_args()
    names = [n for n in train_names() if a.only in n]
    with ProcessPoolExecutor(a.j, mp_context=multiprocessing.get_context("fork")) as ex:
        res = {n: (o, dt) for n, o, dt in ex.map(bench.run_one, [(a.algo, n) for n in names])}
    s = bench.summarize(res)
    out = {"summary": s, "images": {n: {"ms": round(dt * 1000), **o} for n, (o, dt) in res.items()}}
    (HERE / "results" / f"{a.algo}{a.tag}.json").write_text(json.dumps(out, indent=1))
    ref = json.loads((LAB / "results" / f"{a.ref}.json").read_text())["images"]
    by = {}
    for n, (o, dt) in res.items():
        f = label(n)["setup"]["font"] or "none"
        g = by.setdefault(f, [0, 0, 0, 0])
        g[0] += len(o["correct"]) + len(o["wrong"]) + len(o["unknown"])
        g[1] += len(o["correct"])
        g[2] += len(o["wrong"]) + len(o["npc"]) + len(o["extra"])
        g[3] += len(ref[n]["correct"]) if n in ref else 0
        bad = {k: o[k] for k in ("wrong", "npc", "extra") if o[k]}
        if bad:
            print("WRONG", n, json.dumps(bad))
        d = len(o["correct"]) - (len(ref[n]["correct"]) if n in ref else 0)
        if d <= -2:
            print(f"LOST {d} {n}")
    for f, (rows, ok, bad, r) in sorted(by.items()):
        print(f"  {f:28s} rows{rows:4d} ok{100 * ok / max(1, rows):6.1f} ref{100 * r / max(1, rows):6.1f} bad{bad:3d}")
    print(a.algo, json.dumps(s))


if __name__ == "__main__":
    main()
