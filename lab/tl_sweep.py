"""tl_sweep.py: open-set policies on results/tl/cache.pkl (CRNN reads).
Prints one tbench summary line per policy."""

import json
import pickle
import re
import sys
from pathlib import Path

from data import label
from rowparse import LETTER
from tbench import score, summarize
from tl_front import clean, valid

CACHE = Path(__file__).parent / "results/tl/cache.pkl"
for _a in sys.argv:
    if _a.startswith("--cache="):
        CACHE = CACHE.with_name(f"cache{_a[8:]}.pkl")
LOOK = {"5": "S", "8": "B", "6": "G", "4": "A"}


def tokens(text: str) -> list[tuple[str, list[int]]]:
    """Words with the indices of their chars in text"""
    out, cur, idx = [], "", []
    for i, ch in enumerate(text):
        if ch == " ":
            if cur:
                out.append((cur, idx))
            cur, idx = "", []
        else:
            cur += ch
            idx.append(i)
    if cur:
        out.append((cur, idx))
    return out


def name_of(text: str, conf: list[float], team: str | None, glued: bool):
    """(name, min conf) from a read: drop [RANK], a 1-char team letter word,
    a glued team letter (glued: the region may start with the letter), and
    words after the name (score / stats)."""
    ws = [w for w in tokens(text) if not (w[0].startswith("[") or w[0].endswith("]"))]
    if ws and len(ws[0][0]) == 1 and len(ws) >= 2:
        ws = ws[1:]
    if not ws:
        return None, 0.0
    w, idx = ws[0]
    if glued and team and len(w) >= 4 and LOOK.get(w[0], w[0].upper()) == LETTER[team]:
        w, idx = w[1:], idx[1:]
    c = min((conf[i] for i in idx), default=0.0)
    return w, c


BY_LETTER = {v: k for k, v in LETTER.items()}
NPC_RE = re.compile(r"^[a-z0-9]{8,10}$")


def policy(img: dict, *, src="name", split=True, glue=True, gate=0, tau=0.0, agree=False,
           teamless=True, glue2=False, inrow=False, rowletter=False, tau_bad=None, ocr=None,
           tau_ocr=0.99, npc=False, both_agree=False, lettercheck=None):
    if img["n_team"] < gate:
        return []
    out = {}
    top = {}
    for r in img["regions"]:
        if r["team"]:
            top[r["col"]] = min(top.get(r["col"], 1 << 30), r["y"])
    for r in img["regions"]:
        # rows sort by team: teamless rows above all team rows are NPCs
        if npc and r["team"] is None and r["y"] < top.get(r["col"], 0) \
                and NPC_RE.match(r["name"][0].strip()):
            continue
        glued = glue and not r["letter"]
        team = r["team"]
        if not split:
            text = clean(r[src][0])
            n, c = text, min(r[src][1], default=0.0)
        elif src == "best":  # name crop and row crop: agree, else the surer read
            n1, c1 = name_of(*r["name"], team, glued)
            n2, c2 = name_of(*r["row"], team, glued)
            if n1 == n2:
                n, c = n1, max(c1, c2)
            elif both_agree:
                continue
            else:
                n, c = (n1, c1) if c1 >= c2 else (n2, c2)
        else:
            n, c = name_of(*r[src], team, glued)
            if agree:
                other = "row" if src == "name" else "name"
                n2, c2 = name_of(*r[other], team, True)
                if n2 != n:
                    continue
                c = max(c, c2)
        if n is None:
            continue
        row = r["row"][0].replace(" ", "")
        # a team letter glued to the name, with no team (or another team) from the parse
        if glue2 and not r["letter"] and len(n) >= 4 and LOOK.get(n[0], n[0]) in BY_LETTER \
                and len(n) > 16:
            n, team = n[1:], BY_LETTER[LOOK.get(n[0], n[0])]
        # team letter = first char of the row read, when the parse has none
        if rowletter and team is None and row and n in row:
            pre = row[: row.index(n)]
            if len(pre) == 1 and LOOK.get(pre, pre) in BY_LETTER:
                team = BY_LETTER[LOOK.get(pre, pre)]
        o = r.get("ocr") or ""
        if ocr == "only":
            n = o
        elif ocr == "agree" and n != o:
            continue
        elif ocr == "agree_ci" and n.lower() != o.lower():
            continue
        elif ocr == "agree_or_conf" and n.lower() != o.lower() and c < tau_ocr:
            continue
        if lettercheck:
            # row read "L name ...": its letter against the parse team
            w0 = r["row"][0].strip().split(" ")[0] if r["row"][0].strip() else ""
            rl = BY_LETTER.get(LOOK.get(w0, w0)) if len(w0) == 1 else None
            if rl and team and rl != team:
                if lettercheck == "drop":
                    team = None
                elif lettercheck == "row":
                    team = rl
                elif lettercheck == "skip":
                    continue
        if not valid(n) or c < tau:
            continue
        # the name read must be inside the row read (two crops agree)
        if inrow and n not in row:
            if tau_bad is None or c < tau_bad:
                continue
        if not teamless and team is None:
            continue
        out.setdefault(n, team)
    return list(out.items())


POLICIES = {
    "P0 name, clean (=t1)": dict(split=False, glue=False),
    "P1 name, split words": dict(glue=False),
    "P2 +strip glued letter": dict(),
    "P3 +gate 3 team rows": dict(gate=3),
    "P4 row crop": dict(src="row", gate=3),
    "P5 name==row agree": dict(gate=3, agree=True),
    "P6 P3 + tau .5": dict(gate=3, tau=0.5),
    "P7 P3 + tau .7": dict(gate=3, tau=0.7),
    "P8 P3 + tau .9": dict(gate=3, tau=0.9),
    "Q1 P3 + glue2": dict(gate=3, glue2=True),
    "Q2 Q1 + rowletter": dict(gate=3, glue2=True, rowletter=True),
    "Q3 Q2 + inrow": dict(gate=3, glue2=True, rowletter=True, inrow=True),
    "Q4 Q3 + inrow unless c>.95": dict(gate=3, glue2=True, rowletter=True, inrow=True, tau_bad=0.95),
    "Q5 Q3 + tau .6": dict(gate=3, glue2=True, rowletter=True, inrow=True, tau=0.6),
    "Q6 Q3 teamed only": dict(gate=3, glue2=True, rowletter=True, inrow=True, teamless=False),
    "S1 Q2 tau .3": dict(gate=3, glue2=True, rowletter=True, tau=0.3),
    "S2 Q2 tau .5": dict(gate=3, glue2=True, rowletter=True, tau=0.5),
    "S3 Q2 tau .7": dict(gate=3, glue2=True, rowletter=True, tau=0.7),
    "S4 Q2 tau .9": dict(gate=3, glue2=True, rowletter=True, tau=0.9),
    "S5 Q2 tau .97": dict(gate=3, glue2=True, rowletter=True, tau=0.97),
    "S6 Q3 tau .9": dict(gate=3, glue2=True, rowletter=True, inrow=True, tau=0.9),
    "V1 Q2 + npc filter": dict(gate=3, glue2=True, rowletter=True, npc=True),
    "V2 V1 + tau .7": dict(gate=3, glue2=True, rowletter=True, npc=True, tau=0.7),
    "V3 V1 + tau .9": dict(gate=3, glue2=True, rowletter=True, npc=True, tau=0.9),
    "W1 row read": dict(src="row", gate=3, glue2=True, rowletter=True, npc=True),
    "W2 best of name/row": dict(src="best", gate=3, glue2=True, rowletter=True, npc=True),
    "W3 name == row": dict(src="best", both_agree=True, gate=3, glue2=True, rowletter=True, npc=True),
    "W4 W2 + tau .7": dict(src="best", gate=3, glue2=True, rowletter=True, npc=True, tau=0.7),
    "W5 W3 + tau .7": dict(src="best", both_agree=True, gate=3, glue2=True, rowletter=True, npc=True, tau=0.7),
    "X1 W2 + letter check: row": dict(src="best", gate=3, glue2=True, rowletter=True, npc=True, lettercheck="row"),
    "X2 W2 + letter check: drop team": dict(src="best", gate=3, glue2=True, rowletter=True, npc=True, lettercheck="drop"),
    "X3 W3 + letter check: row": dict(src="best", both_agree=True, gate=3, glue2=True, rowletter=True, npc=True,
                                      lettercheck="row"),
    "X4 X1 + tau .7": dict(src="best", gate=3, glue2=True, rowletter=True, npc=True, lettercheck="row", tau=0.7),
    "R1 OCR only": dict(gate=3, rowletter=True, ocr="only"),
    "R2 CRNN == OCR": dict(gate=3, glue2=True, rowletter=True, ocr="agree"),
    "R3 CRNN ~= OCR (case)": dict(gate=3, glue2=True, rowletter=True, ocr="agree_ci"),
    "R4 R3 or conf .99": dict(gate=3, glue2=True, rowletter=True, ocr="agree_or_conf"),
    "R5 R3 or conf .999": dict(gate=3, glue2=True, rowletter=True, ocr="agree_or_conf", tau_ocr=0.999),
}


def run(kw: dict) -> tuple[dict, dict]:
    cache = pickle.loads(CACHE.read_bytes())
    res = {n: (score(label(n), policy(img, **kw)), img["ms"] / 1000) for n, img in cache.items()}
    return summarize(res), res


if __name__ == "__main__":
    keys = ["exact", "full", "w_full", "wteam", "bad_reads", "precision", "w_precision", "images_all_right",
            "snap_correct", "snap_w_correct", "snap_wrong"]
    dump = [a for a in sys.argv[1:] if a.startswith("--") and not a.startswith("--cache")]
    sel = [a for a in sys.argv[1:] if not a.startswith("--")]
    sel = [p for p in POLICIES if any(p.startswith(s) for s in sel)] or list(POLICIES)
    for name in sel:
        s, res = run(POLICIES[name])
        print(f"{name:28s}", json.dumps({k: s[k] for k in keys}))
        for key in (d[2:] for d in dump):
            for n, (o, _) in sorted(res.items()):
                if o[key]:
                    print(f"   {key} {n}: {o[key]}")
