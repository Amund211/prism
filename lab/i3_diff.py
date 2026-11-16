"""i3_diff.py A B: rows that changed outcome from results/A.json to results/B.json."""

import json
import sys
from pathlib import Path

R = Path(__file__).parent / "results"


def main():
    a = json.loads((R / f"{sys.argv[1]}.json").read_text())["images"]
    b = json.loads((R / f"{sys.argv[2]}.json").read_text())["images"]
    for img in sorted(b):
        if img not in a:
            continue
        for k in ("correct", "wrong", "npc", "extra"):
            new = set(b[img][k]) - set(a[img][k])
            for n in sorted(new):
                print(k, img, n, b[img][k][n])
        lost = set(a[img]["correct"]) - set(b[img]["correct"])
        for n in sorted(lost):
            print("lost", img, n)


if __name__ == "__main__":
    main()
