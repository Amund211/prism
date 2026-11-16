"""Stage 1+2 check, no names: team multiset from parsed rows vs labels."""

import multiprocessing
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor

from common import parse
from data import image, label, train_names


def one(n: str) -> tuple[str, Counter, Counter, int]:
    lab = label(n)
    tab, prows = parse(image(n))
    got = Counter(p.team for p in prows if p.team)
    want = Counter(r["team"] for r in lab["rows"] if r["team"])
    return n, got, want, tab.k if tab else 0


def main() -> None:
    names = [n for n in train_names() if (sys.argv[1] if len(sys.argv) > 1 else "") in n]
    tp = fp = fn = 0
    by: dict[str, list[int]] = {}
    with ProcessPoolExecutor(11, mp_context=multiprocessing.get_context("fork")) as ex:
        for n, got, want, k in ex.map(one, names):
            t = sum((got & want).values())
            p = sum((got - want).values())
            f = sum((want - got).values())
            tp, fp, fn = tp + t, fp + p, fn + f
            font = label(n)["setup"]["font"] or "none"
            g = by.setdefault(font, [0, 0, 0])
            g[0] += t
            g[1] += p
            g[2] += f
            if p or f:
                print(f"{n:70s} k{k} extra {dict(got - want)} missing {dict(want - got)}")
    for font, (t, p, f) in sorted(by.items()):
        print(f"  {font:34s} found {t:4d} extra {p:3d} missing {f:4d}")
    print(f"teams found {tp} extra {fp} missing {fn} recall {tp / max(1, tp + fn):.3f}")


if __name__ == "__main__":
    main()
