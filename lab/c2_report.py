"""c2_report.py CACHE... [--pol V1,V2,W2]: one line per (cache, policy):
full, w_full, bad reads, precision, w_precision, snap, hybrid found / false new"""

import pickle
import sys
from pathlib import Path

import tl_hybrid
import tl_sweep
from data import label

args = [a for a in sys.argv[1:] if not a.startswith("--")]
pols = next((a[6:] for a in sys.argv[1:] if a.startswith("--pol=")), "V1,V2,W1,W2,W3,W5").split(",")
print(f"{'cache':22s} {'pol':4s} {'full':>5s} {'w_full':>6s} {'bad':>4s} {'prec':>5s} {'w_prec':>6s} "
      f"{'snap':>5s} {'s_wr':>4s} {'h_found':>7s} {'h_false':>7s}")
for c in args:
    tl_sweep.CACHE = Path(c) if c.endswith(".pkl") else tl_sweep.CACHE.with_name(f"cache{c}.pkl")
    cache = pickle.loads(tl_sweep.CACHE.read_bytes())
    for p in pols:
        kw = tl_sweep.POLICIES[next(k for k in tl_sweep.POLICIES if k.startswith(p + " "))]
        s, _ = tl_sweep.run(kw)
        found = tried = fn = imgs = 0
        for name, img in cache.items():
            lab = label(name)
            if not lab["rows"]:
                continue
            imgs += 1
            reads = tl_sweep.policy(img, **kw)
            rows = {r["name"] for r in lab["rows"]}
            known = list(lab["known"])
            fn += sum(1 for n, _ in tl_hybrid.new_reads(reads, known) if n not in rows)
            for d in rows:
                tried += 1
                found += d in dict(tl_hybrid.new_reads(reads, [k for k in known if k != d]))
        print(f"{c or '(i4 full)':22s} {p:4s} {s['full']:5.1f} {s['w_full']:6.1f} {s['bad_reads']:4d} "
              f"{s['precision']:5.1f} {s['w_precision']:6.1f} {s['snap_correct']:5.1f} {s['snap_wrong']:4d} "
              f"{100 * found / tried:7.1f} {fn / imgs:7.2f}")
