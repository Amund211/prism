"""I4: make folds (font families, for leave-own-font-out) and the synthetic
dataset. Usage: i4_gen.py N  -> results/i4/{folds.json,data.pkl,preview.png}"""

import json
import multiprocessing
import pickle
import sys
from pathlib import Path

import cv2
import numpy as np

from data import label, train_names
from g_bank import bank, excluded_for
from i4_synth import fonts_weighted, sample

OUT = Path(__file__).parent / "results/i4"
NFOLD = 3


def folds() -> list[list[str]]:
    fs = [f for f in bank() if f.fid != "vanilla"]
    fam_of = {f.fid: f.family for f in fs}
    groups: list[set[str]] = []  # sets of families
    count: list[int] = []
    for n in train_names():
        ex = excluded_for(label(n)["setup"]["font"])
        if not ex:
            continue
        fams = {fam_of[i] for i in ex if i in fam_of}
        hit = [i for i, g in enumerate(groups) if g & fams]
        new, c = set(fams), 1
        for i in sorted(hit, reverse=True):
            new |= groups.pop(i)
            c += count.pop(i)
        groups.append(new)
        count.append(c)
    covered = set().union(*groups) if groups else set()
    rest = sorted({f.family for f in fs} - covered)
    order = sorted(range(len(groups)), key=lambda i: -count[i])
    out: list[set[str]] = [set() for _ in range(NFOLD)]
    load = [0] * NFOLD
    for i in order:
        j = int(np.argmin(load))
        out[j] |= groups[i]
        load[j] += count[i]
    for i, fam in enumerate(rest):
        out[i % NFOLD].add(fam)
    print("fold image loads", load)
    return [sorted({f.fid for f in fs if f.family in o}) for o in out]


def work(args: tuple[int, int]) -> list:
    seed, n = args
    rng = np.random.default_rng(seed)
    fs, p = fonts_weighted()
    out = []
    for _ in range(n):
        f = fs[int(rng.choice(len(fs), p=p))]
        img, text = sample(rng, f)
        out.append((img, text, f.fid))
    return out


def main() -> None:
    n = int(sys.argv[1])
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "folds.json").write_text(json.dumps(folds()))
    per = 2000
    jobs = [(s, per) for s in range(n // per)]
    with multiprocessing.get_context("fork").Pool(4) as pool:
        data = [x for part in pool.map(work, jobs) for x in part]
    (OUT / "data.pkl").write_bytes(pickle.dumps(data))
    rows = [cv2.resize(d[0], (240, 20)) for d in data[:40]]
    cv2.imwrite(str(OUT / "preview.png"), cv2.cvtColor(np.vstack(rows), cv2.COLOR_RGB2BGR))
    print(len(data), "samples;", [d[1] for d in data[:8]])


if __name__ == "__main__":
    main()
