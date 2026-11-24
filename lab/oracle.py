"""oracle.py [-j N] [--only s]: oracle ladder on the grid pipeline (j2_bg, shadow mask).

Aligned image: the grid fits the label (no NPC rows, cell count fits), so label
row i is grid cell i (column-major, as GuiPlayerTabOverlay fills it). Each label
row of an aligned image gets the first stage that loses it. Steps:
  s0      j2_bg as is (all images)
  s_team  same parse, label team on every parsed row with a name word
  c_real  perfect matcher on the real parse (name word + right team)
  c_team  perfect matcher, label team (name word only)
"""

import argparse
import json
import multiprocessing
import os
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ["J_MASK"] = "shadow"
os.environ["J_WMASK"] = "0"

from bench import outcome, summarize  # noqa: E402
from data import image, label, load_weights, train_names  # noqa: E402
from j3_slot import grid_parse, match, read_teams  # noqa: E402

RESULTS = Path(__file__).parent / "results"
STAGES = ["no_text", "no_name", "no_letter", "bad_team", "not_known", "m_unknown", "m_wrong", "ok"]
# letter slot is always on now; the slot-off run ("oracle" tag) needs branch tabcap-tablist
TAG = "oracle_slot"


def why_unaligned(name, lab, g):
    if "lunar" in name:
        return "lunar"
    want = len(lab["rows"])
    if want == 0:
        return "no_rows"
    if lab["npcs"]:
        return "npcs"
    if g is None:
        return "no_grid"
    got, nc = len(g.tops), len(g.cols)
    if nc == 1 and got != want or nc > 1 and not (got * nc >= want > got * (nc - 1)):
        return "grid_count"
    return None


def run(name):
    lab = label(name)
    known = list(lab["known"])
    rgb = image(name)
    real = dict(read_teams(rgb, known))
    o0 = outcome(lab, real)
    g, tab, prows = grid_parse(rgb)
    why = why_unaligned(name, lab, g)
    res = {"why": why, "s0": o0}
    if why is not None or tab is None:
        res["why"] = why or "no_text"
        return name, res
    nt = len(g.tops)
    cell = {(p.row.col, p.row.y): p for p in prows}
    by_row = {}
    for i, r in enumerate(lab["rows"]):
        by_row[r["name"]] = cell.get((i // nt, g.tops[i % nt])), (i // nt, g.tops[i % nt]), r["team"]
    tab_rows = {(r.col, r.y) for r in tab.rows}
    stages = {}
    c_real, c_team = {}, {}
    for n, (p, key, team) in by_row.items():
        # label team None (spectator, respawning) is correct when no team is read
        if n in o0["correct"]:
            st = "ok"
        elif key not in tab_rows:
            st = "no_text"
        elif p is None or p.name is None:
            st = "no_name"
        elif p.team != team:
            st = "no_letter" if p.team is None else "bad_team"
        elif n not in known:
            st = "not_known"
        elif n in o0["wrong"]:
            st = "m_wrong"
        else:
            st = "m_unknown"
        stages[n] = st
        if p is not None and p.name is not None and n in known:
            c_team[n] = team
            if p.team == team:
                c_real[n] = team
    # alignment check: rows g2 read as the right name sit in the expected cell
    _, gh = match(rgb, known, tab, prows)
    agree = Counter()
    for n, (_, p) in gh.items():
        if n in by_row:
            agree["same" if (p.row.col, p.row.y) == by_row[n][1] else "diff"] += 1
    for p in prows:
        if p.name is None:
            continue
        hit = [n for n, v in by_row.items() if v[0] is p]
        p.team = by_row[hit[0]][2] if hit else p.team
    s_team, _ = match(rgb, known, tab, prows)
    res.update(stages=stages, agree=dict(agree), s_team=outcome(lab, s_team),
               c_real=outcome(lab, c_real), c_team=outcome(lab, c_team))
    return name, res


def group(name, lab):
    if "lunar" in name:
        return "lunar"
    f = lab["setup"]["font"] or "none"
    return f.removeprefix("pack:").split("-")[0]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("-j", type=int, default=6)
    p.add_argument("--only", default="")
    a = p.parse_args()
    names = [n for n in train_names() if a.only in n]
    with ProcessPoolExecutor(a.j, mp_context=multiprocessing.get_context("fork")) as ex:
        res = dict(ex.map(run, names))
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"{TAG}.json").write_text(json.dumps(res, indent=1))
    report(res)


def report(res):
    W = load_weights()
    al = [n for n, r in res.items() if r["why"] is None]
    print(f"aligned images {len(al)} / {len(res)}; unaligned:", dict(Counter(r["why"] for r in res.values() if r["why"])))
    ag = Counter()
    for n in al:
        ag.update(res[n]["agree"])
    print("alignment check (g2 hits in the expected cell):", dict(ag))

    def summ(names, step):
        return summarize({n: (res[n][step], 0.0) for n in names})

    print("\nladder        all rows      aligned rows   (correct % / weighted correct % / wrong)")
    for step in ["s0", "s_team", "c_real", "c_team"]:
        s = summ(al, step)
        line = f"  {step:8s}"
        if step == "s0":
            t = summ(list(res), step)
            line += f"  {t['correct']:5.1f} / {t['w_correct']:5.1f} / {t['n_wrong']}"
        else:
            line += " " * 22
        print(line + f"   {s['correct']:5.1f} / {s['w_correct']:5.1f} / {s['n_wrong']}  rows {s['rows']}")

    print("\nunaligned images, s0:")
    for why in sorted({r["why"] for r in res.values() if r["why"]}):
        ns = [n for n, r in res.items() if r["why"] == why]
        s = summ(ns, "s0")
        print(f"  {why:11s} imgs {len(ns):3d} rows {s['rows']:4d} correct {s['correct']:5.1f} w {s['w_correct']:5.1f}")

    print("\nstage that loses each row (aligned images), % of rows; w = weighted:")
    by = {}
    for n in al:
        g = group(n, label(n))
        for st in res[n]["stages"].values():
            by.setdefault(g, Counter())[st] += 1
            by.setdefault("ALL", Counter())[st] += 1
            by.setdefault("ALL_w", Counter())[st] += W[n]
    print(f"  {'group':14s} {'rows':>6s} " + " ".join(f"{s:>9s}" for s in STAGES))
    for g in ["ALL", "ALL_w"] + sorted(k for k in by if not k.startswith("ALL")):
        c = by[g]
        tot = sum(c.values())
        print(f"  {g:14s} {tot:6.0f} " + " ".join(f"{100 * c[s] / tot:9.1f}" for s in STAGES))


if __name__ == "__main__":
    main()
