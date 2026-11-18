"""u_snap.py [--cache=SUFFIX]: snap-to-known (closed set) with other costs on
the ucache log-probs. Team per region as X2 (parse team, row-letter check,
row letter when no team, NPC rule, gate 3). Costs, region x known name:
  lev     i4 cost on the X2 read (= tbench.snap)
  ctc     CTC cost of the name on the name crop (i4_rec.ctc_cost)
  min     min(lev, ctc)
  lr      lev, but a pair must also pass a likelihood ratio: NLL(name) -
          NLL(best read) per char <= d on the name crop
"""

import json
import pickle
import sys
from pathlib import Path

import numpy as np

import tl_sweep
from bench import outcome
from common import assign
from data import label, load_weights
from i4_rec import cost, ctc_cost, ctc_nll
from tl_sweep import BY_LETTER, LOOK, NPC_RE, name_of

SUF = next((a[8:] for a in sys.argv if a.startswith("--cache=")), "")
CACHE = Path(__file__).parent / f"results/tl/ucache{SUF}.pkl"


def team_of(r):
    team = r["team"]
    w0 = r["row"][0].strip().split(" ")[0] if r["row"][0].strip() else ""
    rl = BY_LETTER.get(LOOK.get(w0, w0)) if len(w0) == 1 else None
    if team is None:
        return rl
    return None if rl and rl != team else team


def regions(img):
    if img["n_team"] < 3:
        return []
    top = {}
    for r in img["regions"]:
        if r["team"]:
            top[r["col"]] = min(top.get(r["col"], 1 << 30), r["y"])
    out = []
    for r in img["regions"]:
        if r["team"] is None and r["y"] < top.get(r["col"], 0) and NPC_RE.match(r["name"][0].strip()):
            continue
        t = team_of(r)
        if not t:
            continue
        glued = not r["letter"]
        n1, c1 = name_of(*r["name"], t, glued)
        n2, c2 = name_of(*r["row"], t, glued)
        n = n1 if (n1 == n2 or c1 >= c2) else n2
        out.append((r, t, n or ""))
    return out


def snap(img, known, kind, max_cost=0.34, margin=0.08, d=1.0):
    regs = regions(img)
    if not regs or not known:
        return {}
    L = np.array([[cost(n, k) for k in known] for _, _, n in regs])
    if kind == "lev":
        C = L
    else:
        X = np.array([ctc_cost(r["lp_name"].astype(np.float64), known) for r, _, _ in regs])
        if kind == "ctc":
            C = X
        elif kind == "min":
            C = np.minimum(L, X)
        elif kind == "mean":
            C = (L + X) / 2
        elif kind == "lr":
            C = L.copy()
            for i, (r, _, _) in enumerate(regs):
                lp = r["lp_name"].astype(np.float64)
                ex = (ctc_nll(lp, known) + lp.max(0).sum()) / np.array([max(3, len(k)) for k in known])
                C[i, ex > d] = 9
    return {known[j]: regs[i][1] for i, j in assign(C, max_cost, margin)}


def main():
    cache = pickle.loads(CACHE.read_bytes())
    w = load_weights()
    grid = [("lev", 0.34, 0.08, 0), ("lev", 0.45, 0.08, 0), ("lev", 0.5, 0.08, 0),
            ("ctc", 0.34, 0.08, 0), ("ctc", 0.5, 0.08, 0), ("ctc", 0.6, 0.08, 0),
            ("min", 0.34, 0.08, 0), ("min", 0.45, 0.08, 0), ("mean", 0.34, 0.08, 0), ("mean", 0.45, 0.08, 0),
            ("lr", 0.5, 0.08, 1.0), ("lr", 0.6, 0.08, 1.0), ("lr", 0.6, 0.08, 2.0), ("lr", 0.7, 0.08, 1.5)]
    for kind, mc, mg, d in grid:
        c = wr = rows = 0
        wc = wrows = 0.0
        for n, img in cache.items():
            lab = label(n)
            o = outcome(lab, snap(img, list(lab["known"]), kind, mc, mg, d))
            c += len(o["correct"])
            wr += len(o["wrong"]) + len(o["npc"]) + len(o["extra"])
            rows += len(lab["rows"])
            wc += w[n] * len(o["correct"])
            wrows += w[n] * len(lab["rows"])
        print(json.dumps({"kind": kind, "max_cost": mc, "margin": mg, "d": d,
                          "correct": round(100 * c / rows, 1), "w_correct": round(100 * wc / wrows, 1),
                          "wrong": wr}), flush=True)


if __name__ == "__main__":
    main()
