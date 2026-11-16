"""d_gate.py <module> <max_cost> <margin>: sweep an image-level gate
(median of the per-row best cost) on the saved tune matrices."""

import pickle
import sys
from pathlib import Path

import numpy as np

from bench import outcome
from common import assign
from data import label

mod, mc, mg = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
data = pickle.loads((Path(__file__).parent / "results" / f"tune_{mod}.pkl").read_bytes())
for q in (0.3, 0.4, 0.5, 0.6, 1.0):
    c = w = 0
    for n, teams, names, C, _ in data:
        got = {}
        if C is not None and C.size and np.median(C.min(axis=1)) <= q:
            for i, j in assign(C, mc, mg):
                if teams[i]:
                    got[names[j]] = teams[i]
        o = outcome(label(n), got)
        c += len(o["correct"])
        w += len(o["wrong"]) + len(o["npc"]) + len(o["extra"])
    print(f"gate {q}: correct {c} wrong {w}")
