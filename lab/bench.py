"""bench.py <algo module> [-j N] [--only substr]: score an algorithm on train.

An algo module has read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str].
Scoring is the same as prism tests/prism/overlay/tabcap/test_samples.py:outcome.
Writes results/<algo>.json with per-image outcome and time.
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

from data import image, label, train_names  # noqa: E402

RESULTS = Path(__file__).parent / "results"


def outcome(lab: dict, got: dict[str, str]) -> dict[str, dict]:
    out: dict[str, dict] = {k: {} for k in ("correct", "wrong", "unknown")}
    for row in lab["rows"]:
        name, team = row["name"], row["team"]
        read = got.get(name)
        if read == team:
            out["correct"][name] = team
        elif read is None:
            out["unknown"][name] = f"label {team}"
        else:
            out["wrong"][name] = f"got {read}, label {team or 'no team'}"
    names = {row["name"] for row in lab["rows"]}
    npcs = set(lab["npcs"])
    out["npc"] = {n: t for n, t in got.items() if n in npcs}
    out["extra"] = {n: t for n, t in got.items() if n not in names | npcs}
    return out


def run_one(args: tuple[str, str]) -> tuple[str, dict, float]:
    algo, name = args
    mod = importlib.import_module(algo)
    lab = label(name)
    rgb = image(name)
    t = time.perf_counter()
    got = mod.read_teams(rgb, list(lab["known"]))
    dt = time.perf_counter() - t
    return name, outcome(lab, dict(got)), dt


def summarize(res: dict[str, tuple[dict, float]]) -> dict:
    c = Counter()
    times = []
    for o, dt in res.values():
        for k, v in o.items():
            c[k] += len(v)
        times.append(dt)
    total = max(1, c["correct"] + c["wrong"] + c["unknown"])
    wrong = c["wrong"] + c["npc"] + c["extra"]
    times.sort()
    return {
        "rows": total,
        "correct": round(100 * c["correct"] / total, 1),
        "wrong": round(100 * wrong / total, 2),
        "unknown": round(100 * c["unknown"] / total, 1),
        "n_wrong": wrong,
        "ms_median": round(1000 * times[len(times) // 2]),
        "ms_p90": round(1000 * times[int(len(times) * 0.9)]),
        "ms_max": round(1000 * times[-1]),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("algo")
    p.add_argument("-j", type=int, default=10)
    p.add_argument("--only", default="")
    p.add_argument("--show", action="store_true", help="print wrong / unknown per image")
    p.add_argument("--groups", action="store_true", help="summary per font")
    a = p.parse_args()
    names = [n for n in train_names() if a.only in n]
    # fork: the sandbox denies the AF_UNIX socket of forkserver
    with ProcessPoolExecutor(a.j, mp_context=multiprocessing.get_context("fork")) as ex:
        res = {n: (o, dt) for n, o, dt in ex.map(run_one, [(a.algo, n) for n in names])}
    s = summarize(res)
    RESULTS.mkdir(exist_ok=True)
    out = {"summary": s, "images": {n: {"ms": round(dt * 1000), **o} for n, (o, dt) in res.items()}}
    (RESULTS / f"{a.algo.replace('.', '_')}.json").write_text(json.dumps(out, indent=1))
    if a.show:
        for n, (o, dt) in sorted(res.items()):
            bad = {k: o[k] for k in ("wrong", "unknown", "npc", "extra") if o[k]}
            if bad:
                print(n, f"{dt*1000:.0f}ms", json.dumps(bad))
    if a.groups:
        by: dict[str, dict] = {}
        for n, v in res.items():
            f = label(n)["setup"]["font"] or "none"
            by.setdefault(f, {})[n] = v
        for f, rr in sorted(by.items()):
            g = summarize(rr)
            print(f"  {f:34s} n{len(rr):3d} rows{g['rows']:4d} ok{g['correct']:6.1f} bad{g['n_wrong']:3d}")
    print(a.algo, json.dumps(s))


if __name__ == "__main__":
    main()
