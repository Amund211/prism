"""i3_gap.py: h5_cascade_ms unknowns vs rows the parse found with a letter."""

import json
from collections import Counter
from pathlib import Path

D = json.load(open("/tmp/claude-1000/i3_seq.json"))
H5 = json.loads((Path(__file__).parent / "results/h5_cascade_ms.json").read_text())["images"]


def main():
    c = Counter()
    for img, d in D.items():
        unk = len(H5[img]["unknown"])
        lab_t = sum(1 for t in d["truth"].values() if t)
        found = sum(1 for r in d["all"] if r[3])
        miss = max(0, lab_t - found)
        c["unknown"] += unk
        c["missing_rows"] += miss
        c["unknown_with_row_found"] += max(0, unk - miss)
        if unk and found >= lab_t:
            c["img_unknown_all_rows_found"] += 1
        if unk:
            c["img_unknown"] += 1
    print(dict(c))


if __name__ == "__main__":
    main()
