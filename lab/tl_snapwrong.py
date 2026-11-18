"""tl_snapwrong.py POLICY CACHE: snap wrong / npc / extra per image"""

import sys

import tl_sweep

tl_sweep.CACHE = tl_sweep.CACHE.with_name(f"cache{sys.argv[2]}.pkl")
kw = tl_sweep.POLICIES[next(k for k in tl_sweep.POLICIES if k.startswith(sys.argv[1] + " "))]
_, res = tl_sweep.run(kw)
for n, (o, _) in sorted(res.items()):
    bad = {k: o["snap"][k] for k in ("wrong", "npc", "extra") if o["snap"][k]}
    if bad:
        print(n, bad)
