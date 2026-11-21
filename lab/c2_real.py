"""C2 real rows: labelled row crops from the train images, for fine-tuning a B
(token) model, in 3 folds by font pack (a fold's model never saw that pack's
real rows). Target = the labelled name and team token; rank and health come
from the v3_tf row read (labels have neither). Rows the read cannot tie to one
label name are skipped; rows with no token, no health and no name near a label
name are negatives (target "").
Usage: c2_real.py  -> results/c2/real_f{0,1,2}.pkl (train rows of the other
folds), results/c2/real_folds.json ({image: fold})."""

import json
import pickle
from collections import Counter
from pathlib import Path

import numpy as np

from c2_synth import TOKEN, TOKEN_TEAM
from data import image, label, train_names
from g_match import regions_of
from i4_synth import norm_crop
from tl_front import front

LAB = Path(__file__).parent
OUT = LAB / "results/c2"
CACHE = LAB / "results/tl/cache_c2_v3_tf.pkl"
K = 3


def lev(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def target(read: str, rows: list[dict]) -> str | None:
    w = read.strip().split(" ")
    tok = w[0] in TOKEN_TEAM
    if tok:
        w = w[1:]
    health = w[-1] if len(w) > 1 and w[-1].isdigit() else None
    if health:
        w = w[:-1]
    if not w or not w[-1]:
        return None
    nm, rank = w[-1], w[:-1]
    d = sorted((lev(nm.lower(), r["name"].lower()), i) for i, r in enumerate(rows))
    if not d:
        return None
    best, i = d[0]
    if best <= max(2, len(rows[i]["name"]) // 4) and (len(d) == 1 or d[1][0] > best):
        r = rows[i]
        parts = ([TOKEN[r["team"]]] if r.get("team") else []) + rank + [r["name"]] + ([health] if health else [])
        return " ".join(parts)
    if best >= 5 and not tok and not health:
        return ""
    return None


def folds(names: list[str]) -> dict[str, int]:
    """font packs -> K folds, greedy by image count"""
    pack = {n: label(n)["setup"].get("font", "?") for n in names}
    load = [0] * K
    fold_of = {}
    for p, c in Counter(pack.values()).most_common():
        f = load.index(min(load))
        fold_of[p] = f
        load[f] += c
    return {n: fold_of[pack[n]] for n in names}


def main() -> None:
    names = train_names()
    fo = folds(names)
    C = pickle.loads(CACHE.read_bytes())
    per = {f: [] for f in range(K)}
    stats = Counter()
    for n in names:
        lb = label(n)
        regs = C[n]["regions"]
        if not regs:
            continue
        rgb = image(n)
        _, tab, prows = front(rgb)
        by_pos = {(g.prow.row.y, g.prow.row.col): g for g in regions_of(rgb, prows, tab.k)}
        for r in regs:
            t = target(r["row"][0], lb["rows"])
            stats["skip" if t is None else "neg" if t == "" else "row"] += 1
            if t is None:
                continue
            g = by_pos[(r["y"], r["col"])]
            per[fo[n]].append((n, (norm_crop(rgb, g.prow.row.y, g.prow.row.x0, g.prow.row.x1, tab.k), t, -1)))
    print(dict(stats), {f: len(v) for f, v in per.items()}, "images per fold", Counter(fo.values()))
    # learning curve: _h = the rows of half the images (seeded), so 1/3 of all real rows per fold model
    half = set(np.random.default_rng(0).permutation(names)[: len(names) // 2])
    for f in range(K):
        train = [s for g in range(K) if g != f for _, s in per[g]]
        (OUT / f"real_f{f}.pkl").write_bytes(pickle.dumps(train))
        h = [s for g in range(K) if g != f for n, s in per[g] if n in half]
        (OUT / f"real_f{f}_h.pkl").write_bytes(pickle.dumps(h))
        print("fold", f, "rows", len(train), "half", len(h))
    (OUT / "real_folds.json").write_text(json.dumps(fo, indent=0))
    ex = [s[1] for _, s in per[0][:12]]
    print("examples", ex)


if __name__ == "__main__":
    main()
