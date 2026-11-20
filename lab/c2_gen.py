"""C2 dataset. Usage: c2_gen.py NAME N ROW_FRAC KDIST VANILLA_W [SEED] [tokens]
tokens: team tokens (c2_synth.TOKEN) in place of the team letter in targets.
-> results/c2/NAME.pkl, NAME_preview.png. Deterministic for the same args.
ROW_FRAC: share of whole-row samples (rest: name crops).
KDIST: base | hard (GUI scale weights, c2_synth.K_DIST).
VANILLA_W: sampling weight of the vanilla font (each bank font: 1)."""

import multiprocessing
import pickle
import sys
from pathlib import Path

import cv2
import numpy as np

from c2_synth import name_sample, row_sample
from g_bank import bank

OUT = Path(__file__).parent / "results/c2"


def work(args):
    seed, n, row_frac, kd, vw, tok = args
    rng = np.random.default_rng(seed)
    fs = list(bank())
    p = np.array([vw if f.fid == "vanilla" else 1.0 for f in fs])
    p /= p.sum()
    out = []
    for _ in range(n):
        f = fs[int(rng.choice(len(fs), p=p))]
        fn = row_sample if rng.random() < row_frac else name_sample
        img, text = fn(rng, f, kd, tok)
        out.append((img, text, f.fid))
    return out


def main():
    name, n, row_frac, kd, vw = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), sys.argv[4], float(sys.argv[5])
    seed = int(sys.argv[6]) if len(sys.argv) > 6 else 0
    tok = len(sys.argv) > 7 and sys.argv[7] == "tokens"
    per = 2000
    jobs = [(seed * 100_000 + s, per, row_frac, kd, vw, tok) for s in range(n // per)]
    with multiprocessing.get_context("fork").Pool(6) as pool:
        data = [x for part in pool.map(work, jobs) for x in part]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.pkl").write_bytes(pickle.dumps(data))
    rows = [cv2.resize(d[0], (360, 20), interpolation=cv2.INTER_NEAREST) for d in data[:40]]
    img = cv2.resize(np.vstack(rows), None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)
    cv2.imwrite(str(OUT / f"{name}_preview.png"), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    print(len(data), "samples;", [d[1] for d in data[:10]])


if __name__ == "__main__":
    main()
