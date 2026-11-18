"""u_ceiling.py: where do snap misses come from? Per labeled row:
  no_region  no region with a team snaps to it even at any cost (front end)
  team_wrong a region snaps (oracle, any cost) but the region team is wrong / none
  read       a region with the right team exists, but lev snap at 0.34 misses it"""

import pickle
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

from data import label
from i4_rec import cost
from u_snap import regions, snap

CACHE = Path(__file__).parent / "results/tl/ucache.pkl"


def main():
    cache = pickle.loads(CACHE.read_bytes())
    c = Counter()
    by_font = {}
    for n, img in cache.items():
        lab = label(n)
        known = list(lab["known"])
        got = snap(img, known, "lev")
        regs = regions(img)
        # oracle: all regions (also teamless), assigned by lev, no gate
        allr = [(r, None, r["name"][0]) for r in img["regions"]]
        orc = {}
        if allr and known:
            C = np.array([[cost(t, k) for k in known] for _, _, t in allr])
            for i, j in zip(*linear_sum_assignment(C)):
                orc[known[j]] = allr[i][0]
        tm = {}
        for r, t, _ in regs:
            tm[id(r)] = t
        f = lab["setup"]["font"] or "none"
        for row in lab["rows"]:
            nm, t = row["name"], row["team"]
            if got.get(nm) == t:
                k = "ok"
            elif nm not in known:
                k = "not_known"
            elif nm not in orc:
                k = "no_region"
            elif img["n_team"] < 3:
                k = "gate"
                if f.startswith("pack:tc0"):
                    print("gate", n, nm, orc[nm]["name"][0], img["finder"], img["n_team"])
            elif tm.get(id(orc[nm])) != t:
                k = "team_wrong_or_none"
            else:
                k = "read"
            c[k] += 1
            by_font.setdefault(f, Counter())[k] += 1
    tot = sum(c.values())
    print({k: f"{v} ({100 * v / tot:.1f} %)" for k, v in c.items()})
    for f, cc in sorted(by_font.items(), key=lambda x: -sum(v for k, v in x[1].items() if k != "ok")):
        print(f"  {f:34s}", dict(cc))


if __name__ == "__main__":
    main()
