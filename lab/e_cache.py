"""e_cache.py <module> <tag> [-j N] [--every M]: OCR all train rows once, cache
texts (per image: row texts + teams) to results/ocr_<tag>.json for offline
threshold sweeps (e_sweep.py)."""

import argparse
import importlib
import json
import multiprocessing
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")

from data import image, label, train_names  # noqa: E402

OUT = Path(__file__).parent / "results"


def one(args: tuple[str, str]) -> tuple[str, dict]:
    modname, n = args
    mod = importlib.import_module(modname)
    rgb = image(n)
    t = time.perf_counter()
    texts, teams = mod.read_texts(rgb)
    return n, {"texts": texts, "teams": teams, "ms": round(1000 * (time.perf_counter() - t))}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("mod")
    p.add_argument("tag")
    p.add_argument("-j", type=int, default=3)
    p.add_argument("--every", type=int, default=1)
    a = p.parse_args()
    names = train_names()[:: a.every]
    with ProcessPoolExecutor(a.j, mp_context=multiprocessing.get_context("fork")) as ex:
        res = dict(ex.map(one, [(a.mod, n) for n in names]))
    OUT.mkdir(exist_ok=True)
    (OUT / f"ocr_{a.tag}.json").write_text(json.dumps(res))
    ms = sorted(v["ms"] for v in res.values())
    print(a.tag, "images", len(res), "ms median", ms[len(ms) // 2])


if __name__ == "__main__":
    main()
