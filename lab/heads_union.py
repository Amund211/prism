"""Head (leave-one-image-out bank) + text reader union, on the usable images.
A head hit gives the row; the team is taken from the label (assumes the
row colour is read right: pipeline team colour is ~0 wrong today)."""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from data import label  # noqa: E402
from heads import dist, load  # noqa: E402

T = 6.0
data = load()
usable = {}
for n, d in data.items():
    lab = label(n)
    if len(d["heads"]) == len(lab["rows"]) and not lab["npcs"] and lab["rows"] and all(h is not None for h in d["heads"]):
        usable[n] = [(r["name"], r["team"], h) for r, h in zip(lab["rows"], d["heads"])]
bank = defaultdict(list)
for n, rows in usable.items():
    for name, _, h in rows:
        bank[name].append((n, h))

for ref in ("h4_union", "h5_cascade_ms"):
    res = json.loads((HERE / "results" / f"{ref}.json").read_text())["images"]
    c = Counter()
    for n, rows in usable.items():
        known = set(label(n)["known"])
        for name, team, h in rows:
            if team is None:
                continue
            c["rows"] += 1
            best = sorted((min(dist(h, hh) for m, hh in bank[cand] if m != n), cand)
                          for cand in known if any(m != n for m, _ in bank.get(cand, [])))
            head_ok = bool(best) and best[0][0] <= T and best[0][1] == name and not (len(best) > 1 and best[1][0] <= T)
            text_ok = name in res[n]["correct"]
            c["text"] += text_ok
            c["head"] += head_ok
            c["union"] += text_ok or head_ok
    r = c["rows"]
    print(f"{ref:14s} team rows {r}: text {100 * c['text'] / r:.1f}  head {100 * c['head'] / r:.1f}  union {100 * c['union'] / r:.1f}")
