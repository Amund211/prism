"""vote2.py A.json B.json: per-name vote of two results (disagree -> unknown).
Also: what B adds to A, per font."""
import json
import sys
from collections import defaultdict

from data import label

a = json.loads(open(sys.argv[1]).read())["images"]
b = json.loads(open(sys.argv[2]).read())["images"]


def got(v):
    out = {n: ("ok", t) for n, t in v["correct"].items()}
    for k in ("wrong", "npc", "extra"):
        for n, t in v[k].items():
            out[n] = ("bad", t)
    return out


rows = ok = bad = add = conflict = 0
by = defaultdict(lambda: [0, 0, 0])
for n in a:
    x, y = got(a[n]), got(b[n])
    nrows = len(a[n]["correct"]) + len(a[n]["wrong"]) + len(a[n]["unknown"])
    rows += nrows
    f = label(n)["setup"]["font"] or "none"
    by[f][0] += nrows
    for name in set(x) | set(y):
        p, q = x.get(name), y.get(name)
        if p and q and p != q:
            conflict += 1
            continue
        r = p or q
        if r[0] == "ok":
            ok += 1
            by[f][1] += 1
            if not p:
                add += 1
                by[f][2] += 1
        else:
            bad += 1
print(f"rows {rows} vote correct {100 * ok / rows:.1f} wrong {bad} conflicts {conflict} added by B {add}")
for f, (r, o, ad) in sorted(by.items()):
    if ad:
        print(f"  {f:30s} rows {r:4d} ok {100 * o / r:5.1f} added {ad}")
