"""u_union.py: one reader for both use cases, scored as one list.
  open   X2 reads (open set, no known)
  snap   snap all team regions to known (lev cost; no validity filter)
  union  snap, then add the open-set read of each region that did not snap
         (valid name, sequence posterior >= tau)
Scored with tbench.score (full = name + team right; bad reads; precision).
Gate: g3 = >= 3 team rows; gfrac = >= 3, or >= 1 and >= half the regions."""

import json
import pickle
import sys
from pathlib import Path

import numpy as np

from common import assign
from data import label
from i4_rec import cost, ctc_cost
from tbench import score, summarize
from tl_front import valid
from tl_sweep import NPC_RE, name_of
from u_snap import team_of

SUF = next((a[8:] for a in sys.argv if a.startswith("--cache=")), "")
UVAR = Path(__file__).parent / f"results/tl/uvar{SUF}.pkl"
UC = Path(__file__).parent / f"results/tl/ucache{SUF}.pkl"


def regs_all(img, gate):
    n = len(img["regions"])
    ok = img["n_team"] >= 3 if gate == "g3" else (img["n_team"] >= 3 or (img["n_team"] >= 1 and 2 * img["n_team"] >= n))
    if not ok:
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
        glued = not r["letter"]
        n1, c1 = name_of(*r["name"], t, glued)
        n2, c2 = name_of(*r["row"], t, glued)
        nm = n1 if (n1 == n2 or c1 >= c2) else n2
        post = r["v"]["greedy_post"][1][0] if r["v"]["greedy_post"][1] else 0.0
        out.append((r, t, nm or "", post))
    return out


def read(img, known, mode, gate="g3", tau=0.0, kind="lev", lp=None):
    regs = regs_all(img, gate)
    snapped, used = {}, set()
    team_regs = [i for i, x in enumerate(regs) if x[1]]
    if mode != "open" and team_regs and known:
        C = np.array([[cost(regs[i][2], k) for k in known] for i in team_regs])
        if kind == "min":
            C = np.minimum(C, np.array([ctc_cost(lp[id(regs[i][0])], known) for i in team_regs]))
        for a, j in assign(C, 0.34, 0.08):
            snapped[known[j]] = regs[team_regs[a]][1]
            used.add(team_regs[a])
    out = dict(snapped)
    if mode in ("open", "union"):
        for i, (r, t, nm, post) in enumerate(regs):
            if i in used or not valid(nm) or post < tau or nm in out:
                continue
            out[nm] = t
    return list(out.items())


def main():
    cache = pickle.loads(UVAR.read_bytes())
    lp = {}
    if "--min" in sys.argv:
        raw = pickle.loads(UC.read_bytes())
        for n, img in raw.items():
            for a, b in zip(img["regions"], cache[n]["regions"]):
                lp[id(b)] = a["lp_name"].astype(np.float64)
    keys = ["full", "w_full", "wteam", "bad_reads", "precision", "w_precision", "images_all_right"]
    runs = [("open", "g3", 0.0), ("snap", "g3", 0.0), ("union", "g3", 0.0), ("union", "g3", 0.7),
            ("union", "g3", 0.9), ("union", "gfrac", 0.0), ("union", "gfrac", 0.7), ("open", "gfrac", 0.0)]
    for mode, gate, tau in runs:
        for kind in (["lev", "min"] if "--min" in sys.argv and mode != "open" else ["lev"]):
            res = {n: (score(label(n), read(img, list(label(n)["known"]), mode, gate, tau, kind, lp)), 0.0)
                   for n, img in cache.items()}
            s = summarize(res)
            print(f"{mode:5s} {gate:5s} tau{tau:4.1f} {kind:3s}", json.dumps({k: s[k] for k in keys}), flush=True)


if __name__ == "__main__":
    main()
