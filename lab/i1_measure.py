"""i1_measure.py [-j N] [--only s]: accuracy of the letter checks on train
layer segments. Truth: a segment whose OCR text matches a labelled name
(no letter check, score >= 0.8) has that row's team (None = no team)."""

import argparse
import json
import multiprocessing
import os
from collections import Counter
from concurrent.futures import ProcessPoolExecutor

os.environ.setdefault("OMP_NUM_THREADS", "1")

import i1_layer as L  # noqa: E402
from data import image, label, train_names  # noqa: E402
from rapidfuzz import fuzz  # noqa: E402

OUT = "/tmp/claude-1000/i1_measure.json"


def ocr_letter(name: str, line: str) -> str | None:
    line = line.replace(" ", "")
    al = fuzz.partial_ratio_alignment(name.lower(), line.lower())
    pre = "".join(c for c in line[: al.dest_start] if c.isalnum()) if al else ""
    if not pre:
        return None
    c = L.h5.LOOK.get(pre[-1], pre[-1])
    return L.rb.BY_LETTER.get(L.h5.LOOK.get(c, c).upper())


def one(n: str) -> list[dict]:
    lab = label(n)
    teams = {r["name"]: r["team"] for r in lab["rows"]}
    out = []
    for ts, layer, sh, col in L.layer_lines(image(n), None):
        sc, nm = max(((L.score(k, t, layer, sh, col, "none"), k) for t in ts for k in teams),
                     default=(0, ""))
        if sc < 0.8:
            continue
        out.append({"img": n, "name": nm, "truth": teams[nm], "layer": layer,
                    "sh": sh, "shape": L.shape_team(sh), "ocr": ocr_letter(nm, ts[0]),
                    "col": col})
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("-j", type=int, default=2)
    p.add_argument("--only", default="")
    a = p.parse_args()
    names = [n for n in train_names() if a.only in n]
    with ProcessPoolExecutor(a.j, mp_context=multiprocessing.get_context("fork")) as ex:
        rows = [r for rs in ex.map(one, names) for r in rs]
    with open(OUT, "w") as f:
        json.dump(rows, f)
    report(rows)


def report(rows: list[dict]) -> None:
    print("segments matched:", len(rows))
    for key in ("shape", "ocr"):
        c = Counter()
        for r in rows:
            got, tr = r[key], r["truth"]
            c[("right" if got == tr else "none" if got is None else "wrong", tr is None)] += 1
        print(key, "team rows:", {k[0]: v for k, v in c.items() if not k[1]},
              "no-team rows:", {k[0]: v for k, v in c.items() if k[1]})
    c = Counter()
    for r in rows:
        if r["truth"] is None:
            continue
        c[("col_ok" if r["col"] else "col_bad", r["truth"] == r["layer"])] += 1
    print("colour check (col, layer==truth):", dict(c))
    c = Counter()
    for r in rows:
        tr = r["truth"]
        sh, oc = r["shape"] == r["layer"], r["ocr"] == r["layer"]
        lay_ok = tr == r["layer"]
        c[("accept" if (sh or oc) else "reject", "layer_right" if lay_ok else "layer_wrong")] += 1
    print("shape OR ocr accept:", dict(c))
    for mi in (0.6, 0.7, 0.8, 0.9):
        for mm in (0.0, 0.05, 0.1):
            L.MIN_IOU, L.MIN_MARGIN = mi, mm
            c = Counter()
            for r in rows:
                st = L.shape_team(tuple(r["sh"]))
                tr = r["truth"]
                c["right" if st == tr else "none" if st is None else "wrong"] += 1
                acc = st == r["layer"] or r["ocr"] == r["layer"]
                c["or_acc_bad" if acc and tr != r["layer"] else "or_acc" if acc else "or_rej"] += 1
            print(f"iou>={mi} margin>={mm}", dict(c))
    bad = [r for r in rows if r["shape"] is not None and r["shape"] != r["truth"]]
    print("shape wrong examples:", json.dumps(bad[:15]))


if __name__ == "__main__":
    main()
