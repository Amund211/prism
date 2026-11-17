"""Compare algorithms on the labeled samples at several resolutions.

usage: evaluate.py [-v] [-d] [-a<algo>] [-r<res>] [filter...]
  algos: A (exact glyph cipher), B (blur-tolerant profiles), AB (A, then B
         with A's teams fixed); add "+" for context deduction (e.g. AB+).
         Default: all.
  res:   1080p (samples/), 720p, 480p. Default: all.
  -d     decoys: every name of every sample is "known".
  -v     per-sample details.

Known names per sample = its labeled players + players of other samples
of the same game (dead players are in /who but not in the tab list).
Truth is per game: a player's team does not change.
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tablearn  # noqa: E402
import tabsoft  # noqa: E402
import tabteams  # noqa: E402

from samples import SAMPLES  # noqa: E402
RES_DIRS = {"1080p": SAMPLES, "720p": SAMPLES / "720p", "480p": SAMPLES / "480p"}
ALGOS = ["A", "B", "AB", "D", "AD", "AD+"]


def players(label: dict) -> set[str]:
    return {r["name"] for r in label["rows"] if not r.get("npc")}


def run_algo(algo: str, rgb: np.ndarray, known: list[str], roster: list[str]) -> dict[str, str]:
    base = algo.rstrip("+")
    got: dict[str, str] = {}
    if "A" in base:
        got = tabteams.read_teams(rgb, known)
    if "B" in base:
        got = {**tabsoft.read_teams(rgb, known, fixed=got), **got}
    if "D" in base or "E" in base:  # E = D + grid rows
        got = {**tablearn.read_teams(rgb, known, fixed=got, grid="E" in base)[0], **got}
    if algo.endswith("+"):
        got = tabsoft.deduce(got, roster)
    return got


def evaluate(algo: str, res: str, decoys: bool, only: list[str], verbose: bool) -> dict:
    labels = json.loads((SAMPLES / "labels.json").read_text())
    st = {"ok": 0, "wrong": 0, "unknown": 0, "extra_ok": 0, "extra_wrong": 0}
    times = []
    for f, label in sorted(labels.items()):
        if only and not any(o in f for o in only):
            continue
        game = set(players(label))
        for other in labels.values():
            if len(players(other) & game) >= 5:
                game |= players(other)
        truth = {
            r["name"]: r["team"]
            for other in labels.values()
            if len(players(other) & game) >= 5  # Skydeaf is in every game
            for r in other["rows"]
            if r["team"] and r["name"] in game
        }
        known = sorted(game)
        if decoys:
            known = sorted(set().union(*(players(o) for o in labels.values())))

        rgb = np.asarray(Image.open(RES_DIRS[res] / f).convert("RGB"))
        t = time.perf_counter()
        got = run_algo(algo, rgb, known, sorted(game))
        times.append((time.perf_counter() - t) * 1000)

        res_st = dict.fromkeys(st, 0)
        notes = []
        visible = set()
        for r in label["rows"]:
            if r.get("npc") or r["team"] is None or r.get("covered"):
                continue
            visible.add(r["name"])
            g = got.get(r["name"])
            if g == r["team"]:
                res_st["ok"] += 1
            elif g is None:
                res_st["unknown"] += 1
            else:
                res_st["wrong"] += 1
                notes.append(f"{r['name']}: WRONG {g} (is {r['team']})")
        for name, g in got.items():
            if name in visible:
                continue
            if truth.get(name) == g:
                res_st["extra_ok"] += 1
            else:
                res_st["extra_wrong"] += 1
                notes.append(f"{name} (not visible): WRONG {g} (is {truth.get(name)})")
        for k in st:
            st[k] += res_st[k]
        if verbose:
            print(
                f"  {f:28} ok{res_st['ok']:3} wrong{res_st['wrong']:2}"
                f" unk{res_st['unknown']:3} extra{res_st['extra_ok']:2}/-{res_st['extra_wrong']}"
                f" {times[-1]:5.0f}ms"
            )
            for n in notes:
                print("      ", n)
    st["ms"] = float(np.median(times)) if times else 0.0
    return st


def fuse(algo: str, res: str, only: list[str], verbose: bool) -> dict:
    """Approach C: all screenshots of a game together.

    Per name: the team all screenshots agree on (conflict -> unknown). For
    D / E the learned font goes on to the next screenshot.
    Score: share of the game's players (with a known team) we know.
    """
    labels = json.loads((SAMPLES / "labels.json").read_text())
    files = sorted(f for f in labels if not only or any(o in f for o in only))
    games: list[list[str]] = []
    for f in files:
        for g in games:
            if any(len(players(labels[f]) & players(labels[o])) >= 5 for o in g):
                g.append(f)
                break
        else:
            games.append([f])
    st = {"ok": 0, "wrong": 0, "unknown": 0, "conflicts": 0}
    for g in games:
        game = set().union(*(players(labels[f]) for f in g))
        truth = {r["name"]: r["team"] for f in g for r in labels[f]["rows"] if r["team"]}
        known = sorted(game)
        votes: dict[str, set[str]] = {}
        font: dict = {}
        for f in g:
            rgb = np.asarray(Image.open(RES_DIRS[res] / f).convert("RGB"))
            base = algo.rstrip("+")
            got: dict[str, str] = {}
            if "A" in base:
                got = tabteams.read_teams(rgb, known)
            if "B" in base:
                got = {**tabsoft.read_teams(rgb, known, fixed=got), **got}
            if "D" in base or "E" in base:
                more, font = tablearn.read_teams(rgb, known, fixed=got, font=font, grid="E" in base)
                got = {**more, **got}
            for n, t in got.items():
                votes.setdefault(n, set()).add(t)
        fused = {n: next(iter(t)) for n, t in votes.items() if len(t) == 1}
        st["conflicts"] += sum(len(t) > 1 for t in votes.values())
        if algo.endswith("+"):
            fused = tabsoft.deduce(fused, known)
        res_st = {"ok": 0, "wrong": 0, "unknown": 0}
        for n, t in truth.items():
            g_t = fused.get(n)
            res_st["ok" if g_t == t else "unknown" if g_t is None else "wrong"] += 1
        for k in res_st:
            st[k] += res_st[k]
        if verbose:
            print(f"  game of {len(g):2} shots, {len(truth):2} players: {res_st}")
    return st


def main() -> None:
    args = sys.argv[1:]
    verbose, decoys = "-v" in args, "-d" in args
    algos = [a[2:] for a in args if a.startswith("-a")] or ALGOS
    ress = [a[2:] for a in args if a.startswith("-r")] or list(RES_DIRS)
    only = [a for a in args if not a.startswith("-")]
    if "-f" in args:
        print(f"{'algo':5} {'res':6} {'players known':>13} {'wrong':>6} {'conflicts':>9}")
        for res in ress:
            for algo in algos:
                s = fuse(algo, res, only, verbose)
                n = max(1, s["ok"] + s["wrong"] + s["unknown"])
                print(f"{algo:5} {res:6} {s['ok'] / n:13.1%} {s['wrong'] / n:6.1%} {s['conflicts']:9}")
        return
    print(f"{'algo':5} {'res':6} {'correct':>8} {'wrong':>6} {'unknown':>8}  {'extra ok/wrong':>14} {'ms':>5}")
    for res in ress:
        for algo in algos:
            if verbose:
                print(f"{algo} {res}")
            s = evaluate(algo, res, decoys, only, verbose)
            n = max(1, s["ok"] + s["wrong"] + s["unknown"])
            print(
                f"{algo:5} {res:6} {s['ok'] / n:8.1%} {s['wrong'] / n:6.1%}"
                f" {s['unknown'] / n:8.1%}  {s['extra_ok']:>9}/{s['extra_wrong']:<4} {s['ms']:5.0f}"
            )


main()
