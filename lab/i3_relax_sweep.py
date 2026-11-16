"""i3_relax_sweep.py: after h4_union, relaxed g2 on left names; gate by
team-size cap (2 when > 4 letter teams are seen). Counts new correct /
wrong per setting on train."""

import json
import multiprocessing
import os
from collections import Counter
from concurrent.futures import ProcessPoolExecutor

os.environ.setdefault("OMP_NUM_THREADS", "1")

from common import assign  # noqa: E402
from data import image, label, train_names  # noqa: E402
from h4_union import fast_union4  # noqa: E402
from i3_sandwich import g2_cost  # noqa: E402

SETTINGS = [(c, m) for c in (0.4, 0.5, 0.6) for m in (0.12, 0.08, 0.05, 0.03)]


def cap_of(prows):
    seen = {p.team for p in prows if p.team}
    return 2 if len(seen) > 4 else None


def one(name):
    lab = label(name)
    known = list(lab["known"])
    truth = {r["name"]: r["team"] for r in lab["rows"]}
    rgb = image(name)
    out, _, tab, prows = fast_union4(rgb, known)
    res = Counter()
    if tab is None or not known:
        return res
    regions, cost = g2_cost(rgb, known, tab, prows)
    if cost is None:
        return res
    cap = cap_of(prows)
    for c, m in SETTINGS:
        cnt = Counter(out.values())
        for i, j in assign(cost, max_cost=c, margin=m):
            n, t = known[j], regions[i].prow.team
            if n in out or not t:
                continue
            ok = truth.get(n) == t
            res[(c, m, "all", ok)] += 1
            if cap is None or cnt[t] < cap:
                cnt[t] += 1
                res[(c, m, "cap", ok)] += 1
    return res


def main():
    with ProcessPoolExecutor(2, mp_context=multiprocessing.get_context("fork")) as ex:
        tot = Counter()
        for r in ex.map(one, train_names()):
            tot.update(r)
    for c, m in SETTINGS:
        for g in ("all", "cap"):
            print(c, m, g, "good", tot[(c, m, g, True)], "bad", tot[(c, m, g, False)])


if __name__ == "__main__":
    main()
