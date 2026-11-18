"""u_choice.py: name crop vs row crop reads, per region with a labeled name:
how often they differ, which is right, and how choice rules do:
  minc  higher min char prob (X2)
  post  higher sequence posterior (N-best of each crop)
  nll   lower summed CTC NLL of the candidate on name crop + row crop
        (row crop scored as the row read with the name word replaced)"""

import pickle
from collections import Counter
from pathlib import Path

import numpy as np

from data import label
from i4_rec import ctc_nll
from tl_sweep import name_of
from u_decode import beam, posterior
from u_snap import team_of

UC = Path(__file__).parent / "results/tl/ucache.pkl"


def main():
    raw = pickle.loads(UC.read_bytes())
    c = Counter()
    for n, img in raw.items():
        rows = {r["name"] for r in label(n)["rows"]}
        for r in img["regions"]:
            t = team_of(r)
            g = not r["letter"]
            n1, c1 = name_of(*r["name"], t, g)
            n2, c2 = name_of(*r["row"], t, g)
            if not n1 or not n2 or n1 == n2:
                continue
            ok1, ok2 = n1 in rows, n2 in rows
            c["differ"] += 1
            c[f"right name {ok1} row {ok2}"] += 1
            if not (ok1 or ok2):
                continue
            ln, lr = r["lp_name"].astype(np.float64), r["lp_row"].astype(np.float64)
            p1, p2 = posterior(beam(ln, 8)), posterior(beam(lr, 8))
            rowt = r["row"][0]
            alt = rowt.replace(n2, n1, 1) if n2 in rowt else rowt
            nm = r["name"][0]
            alt_n = nm.replace(n1, n2, 1) if n1 in nm else nm
            s1 = ctc_nll(ln, [nm])[0] + ctc_nll(lr, [alt])[0]
            s2 = ctc_nll(ln, [alt_n])[0] + ctc_nll(lr, [rowt])[0]
            for rule, pick1 in (("minc", c1 >= c2), ("post", p1 >= p2), ("nll", s1 <= s2)):
                c[f"{rule} right"] += (ok1 if pick1 else ok2)
    for k, v in sorted(c.items()):
        print(f"{k:28s} {v}")


if __name__ == "__main__":
    main()
