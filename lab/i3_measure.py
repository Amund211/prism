"""i3_measure.py: measure tab-list structure on train (labels + g2 hits).

Writes /tmp/claude-1000/i3_seq.json: per image the sequence of matched
rows (col, y, name, team) sorted down-then-across, plus label info.
"""

import json
import multiprocessing
import os
import sys
from concurrent.futures import ProcessPoolExecutor

os.environ.setdefault("OMP_NUM_THREADS", "1")

from common import parse  # noqa: E402
from data import image, label, train_names  # noqa: E402
from h_common import g2_rows  # noqa: E402

OUT = "/tmp/claude-1000/i3_seq.json"


def one(name: str):
    lab = label(name)
    rgb = image(name)
    tab, prows = parse(rgb)
    truth = {r["name"]: r["team"] for r in lab["rows"]}
    rows = []
    if tab is not None:
        g = g2_rows(rgb, list(lab["known"]), tab, prows)
        for n, (t, p) in g.items():
            if truth.get(n) == t:
                rows.append((p.row.col, p.row.y, p.row.x0, n, t))
        allrows = [(p.row.col, p.row.y, p.row.x0, p.team) for p in prows]
    else:
        allrows = []
    rows.sort()
    allrows.sort()
    return name, {
        "mode": lab["setup"].get("mode"),
        "truth": truth,
        "rows": rows,
        "all": allrows,
        "k": tab.k if tab else None,
    }


def main():
    names = train_names()
    with ProcessPoolExecutor(int(sys.argv[1]) if len(sys.argv) > 1 else 2,
                             mp_context=multiprocessing.get_context("fork")) as ex:
        res = dict(ex.map(one, names))
    with open(OUT, "w") as f:
        json.dump(res, f)
    print("wrote", OUT, len(res))


if __name__ == "__main__":
    main()
