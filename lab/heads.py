"""Head fingerprints: the 8x8 skin face left of each tab row is the same in
every font / pack / GUI scale. Test: leave-one-image-out head -> name.

heads.py            run the leave-one-image-out test
heads.py montage s  save a montage of heads for images matching s
"""
import pickle
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
OUT = HERE / "results"  # gitignored: cache and crops
import grid3  # noqa: E402
from data import image, label, train_names  # noqa: E402


def heads_of(rgb, g):
    """8x8x3 head per grid row (centre sample of each GUI px), and x0"""
    k = g.k
    x0 = min(a for a, _ in g.cols)
    out = []
    for y in g.tops:
        h = rgb[y : y + 8 * k, max(0, x0) : x0 + 8 * k]
        if h.shape[:2] != (8 * k, 8 * k):
            out.append(None)
            continue
        out.append(h[k // 2 :: k, k // 2 :: k].copy())
    return out, x0


def dist(a, b):
    return float(np.abs(a.astype(np.int16) - b.astype(np.int16)).mean())


def load():
    cache = OUT / "heads.pkl"
    if cache.exists():
        return pickle.loads(cache.read_bytes())
    data = {}
    for n in train_names():
        lab = label(n)
        rgb = image(n)
        g = grid3.find_grid(rgb)
        if g is None:
            continue
        hs, x0 = heads_of(rgb, g)
        data[n] = {"k": g.k, "heads": hs, "ncol": len(g.cols)}
    cache.write_bytes(pickle.dumps(data))
    return data


def main():
    data = load()
    # usable: grid rows == label rows, no npcs (row i <-> label row i)
    usable = {}
    for n, d in data.items():
        lab = label(n)
        if len(d["heads"]) == len(lab["rows"]) and not lab["npcs"] and lab["rows"] and all(h is not None for h in d["heads"]):
            usable[n] = [(r["name"], r["team"], h) for r, h in zip(lab["rows"], d["heads"])]
    print("images with grid", len(data), "usable (aligned with labels)", len(usable))
    bank = defaultdict(list)  # name -> [(image, head)]
    for n, rows in usable.items():
        for name, _, h in rows:
            bank[name].append((n, h))
    c = Counter()
    T = 6.0
    for n, rows in usable.items():
        lab = label(n)
        known = set(lab["known"])
        ov = (lab.get("overlay") or {}).get("over_tab")
        for name, team, h in rows:
            c["rows"] += 1
            # candidates: all known names of this image with a head in another image
            best = []
            for cand in known:
                ds = [dist(h, hh) for m, hh in bank.get(cand, []) if m != n]
                if ds:
                    best.append((min(ds), cand))
            best.sort()
            has = any(cand == name for _, cand in best)
            c["has_bank"] += has
            if not best or best[0][0] > T:
                c["unknown"] += 1
                c["unknown_has_bank"] += has
                c["unknown_covered"] += bool(ov) and has
                continue
            # ambiguous: second-best other name also close (same default skin)
            if len(best) > 1 and best[1][0] <= T:
                c["ambiguous"] += 1
                continue
            if best[0][1] == name:
                c["correct"] += 1
            else:
                c["wrong"] += 1
                print("WRONG", n, name, "->", best[0])
    print(sorted(c.items()))
    r = c["rows"]
    print(f"correct {100 * c['correct'] / r:.1f} % of rows; of rows with a bank head: {100 * c['correct'] / max(1, c['has_bank']):.1f} %")


def montage(sub):
    for n in train_names():
        if sub not in n:
            continue
        rgb = image(n)
        g = grid3.find_grid(rgb)
        hs, x0 = heads_of(rgb, g)
        k = g.k
        strip = [rgb[y : y + 8 * k, x0 - 4 * k : x0 + 40 * k] for y in g.tops]
        im = np.concatenate(strip, axis=0)
        f = max(1, 6 // k)
        im = cv2.resize(im, None, fx=f, fy=f, interpolation=cv2.INTER_NEAREST)
        (OUT / "crops").mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(OUT / "crops" / f"heads_{n}.png"), im[..., ::-1])
        print(n, "k", k, "x0", x0, "cols", g.cols)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "montage":
        montage(sys.argv[2])
    else:
        main()
