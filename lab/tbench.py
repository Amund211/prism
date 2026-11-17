"""tbench.py <module> [-j N] [--only s] [--show] [--groups]: score an open-set
tab-list reader on train.

A module has read_tab(rgb) -> list[(name, team | None)]. No known names.
Per labeled row:
  exact   a read name equals the label name (case-sensitive)
  near    Levenshtein <= 1, case-insensitive (snap-able)
  full    exact name and the same team (None = None)
  wteam   exact name, other team
Per read: extra = matches no row / npc within near; npc = an npc name.
snap: map each read to the closest known name (cost <= 0.34, i4 cost) and
score teams like bench.py (closed set; compare with j4_slotping).
"""

import argparse
import importlib
import json
import multiprocessing
import os
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import numpy as np  # noqa: E402
from rapidfuzz.distance import Levenshtein  # noqa: E402

from bench import outcome  # noqa: E402
from common import assign  # noqa: E402
from data import image, label, load_weights, train_names  # noqa: E402
from i4_rec import cost  # noqa: E402

RESULTS = Path(__file__).parent / "results/tl"


def near(a: str, b: str) -> bool:
    return Levenshtein.distance(a.lower(), b.lower()) <= 1


def snap(reads: list[tuple[str, str | None]], known: list[str]) -> dict[str, str]:
    reads = [r for r in reads if r[1]]
    if not reads or not known:
        return {}
    C = np.array([[cost(t, n) for n in known] for t, _ in reads])
    return {known[j]: reads[i][1] for i, j in assign(C, 0.34, 0.08)}


def score(lab: dict, reads: list[tuple[str, str | None]]) -> dict:
    o: dict = {k: [] for k in ("exact", "near", "full", "wteam", "miss", "extra", "npc", "dup")}
    names = [r["name"] for r in lab["rows"]]
    seen = Counter(n for n, _ in reads)
    o["dup"] = [n for n, c in seen.items() if c > 1]
    by = {n: t for n, t in reads}
    for r in lab["rows"]:
        n, t = r["name"], r["team"]
        if n in by:
            o["exact"].append(n)
            (o["full"] if by[n] == t else o["wteam"]).append(f"{n}:{by[n]}/{t}")
        elif any(near(n, x) for x in by):
            o["near"].append(f"{n}~{next(x for x in by if near(n, x))}")
        else:
            o["miss"].append(n)
    for n, t in reads:
        if n in lab["npcs"]:
            o["npc"].append(n)
        elif not any(near(n, x) for x in names):
            o["extra"].append(f"{n}:{t}")
    o["snap"] = outcome(lab, snap(reads, list(lab["known"])))
    o["n_reads"] = len(reads)
    o["n_good"] = sum(1 for n, _ in reads if n in names)
    return o


def run_one(args):
    algo, name = args
    mod = importlib.import_module(algo)
    lab = label(name)
    rgb = image(name)
    t = time.perf_counter()
    reads = [(n, t) for n, t in mod.read_tab(rgb)]
    dt = time.perf_counter() - t
    return name, score(lab, reads), dt


def summarize(res: dict) -> dict:
    c, wc = Counter(), Counter()
    weights = load_weights()
    times, imgs_ok, n_img = [], 0, 0
    for name, (o, dt) in res.items():
        w = weights[name]
        rows = len(label(name)["rows"])
        for k in ("exact", "near", "full", "wteam", "miss", "extra", "npc"):
            c[k] += len(o[k])
            wc[k] += w * len(o[k])
        for k in ("correct", "wrong", "unknown", "npc", "extra"):
            c["s_" + k] += len(o["snap"][k])
            wc["s_" + k] += w * len(o["snap"][k])
        c["rows"] += rows
        wc["rows"] += w * rows
        for k in ("n_reads", "n_good"):
            c[k] += o[k]
            wc[k] += w * o[k]
        if rows:
            n_img += 1
            imgs_ok += len(o["full"]) == rows and not o["extra"] and not o["npc"]
        times.append(dt)
    times.sort()
    R, WR = max(1, c["rows"]), max(1e-9, wc["rows"])
    pct = lambda x, t: round(100 * x / t, 1)  # noqa: E731
    return {
        "rows": c["rows"],
        "exact": pct(c["exact"], R),
        "exact_or_near": pct(c["exact"] + c["near"], R),
        "full": pct(c["full"], R),
        "w_full": pct(wc["full"], WR),
        "wteam": pct(c["wteam"], R),
        "extra_reads": c["extra"] + c["npc"],
        "bad_reads": c["n_reads"] - c["n_good"],
        "precision": pct(c["n_good"], max(1, c["n_reads"])),
        "w_precision": pct(wc["n_good"], max(1e-9, wc["n_reads"])),
        "images_all_right": f"{imgs_ok}/{n_img}",
        "snap_correct": pct(c["s_correct"], R),
        "snap_w_correct": pct(wc["s_correct"], WR),
        "snap_wrong": c["s_wrong"] + c["s_npc"] + c["s_extra"],
        "ms_median": round(1000 * times[len(times) // 2]),
        "ms_p90": round(1000 * times[int(len(times) * 0.9)]),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("algo")
    p.add_argument("-j", type=int, default=3)
    p.add_argument("--only", default="")
    p.add_argument("--show", action="store_true")
    p.add_argument("--groups", action="store_true")
    a = p.parse_args()
    names = [n for n in train_names() if a.only in n]
    with ProcessPoolExecutor(a.j, mp_context=multiprocessing.get_context("fork")) as ex:
        res = {n: (o, dt) for n, o, dt in ex.map(run_one, [(a.algo, n) for n in names])}
    s = summarize(res)
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = {"summary": s, "images": {n: {"ms": round(dt * 1000), **o} for n, (o, dt) in res.items()}}
    (RESULTS / f"{a.algo}.json").write_text(json.dumps(out, indent=1))
    if a.show:
        for n, (o, dt) in sorted(res.items()):
            bad = {k: o[k] for k in ("near", "wteam", "miss", "extra", "npc") if o[k]}
            if bad:
                print(n, json.dumps(bad))
    if a.groups:
        by: dict = {}
        for n, v in res.items():
            by.setdefault(label(n)["setup"]["font"] or "none", {})[n] = v
        for f, rr in sorted(by.items()):
            g = summarize(rr)
            print(f"  {f:34s} n{len(rr):3d} rows{g['rows']:4d} exact{g['exact']:6.1f} "
                  f"full{g['full']:6.1f} extra{g['extra_reads']:3d}")
    print(a.algo, json.dumps(s))


if __name__ == "__main__":
    main()
