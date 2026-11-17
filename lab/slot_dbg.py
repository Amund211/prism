"""slot_dbg.py [font substr] [--save]: why slot_team fails on no_letter rows
(from results/oracle_slot.json). --save writes crops to /tmp/claude-1000/slot/."""

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

from bgmask import bg_mask
from data import image, label
from j3_slot import grid_parse, slot_team

RES = json.loads((Path(__file__).parent / "results/oracle_slot.json").read_text())
OUT = Path("/tmp/claude-1000/slot")


def main():
    only = next((a for a in sys.argv[1:] if not a.startswith("--")), "")
    save = "--save" in sys.argv
    OUT.mkdir(parents=True, exist_ok=True)
    why = Counter()
    for n, r in sorted(RES.items()):
        if r["why"] or only not in n:
            continue
        bad = [m for m, s in r["stages"].items() if s == "no_letter"]
        if not bad:
            continue
        lab = label(n)
        rgb = image(n)
        g, tab, prows = grid_parse(rgb, slot=False)
        bm = bg_mask(rgb, g)
        k, nt = g.k, len(g.tops)
        cell = {(p.row.col, p.row.y): p for p in prows}
        idx = {row["name"]: i for i, row in enumerate(lab["rows"])}
        for m in bad:
            i = idx[m]
            p = cell[(i // nt, g.tops[i % nt])]
            x0 = g.cols[p.row.col][0]
            t, w = slot_team(rgb, bm, p, x0 + 9 * k, k)
            team = lab["rows"][i]["team"]
            why[w] += 1
            print(f"{n[:60]:60s} {m:16s} label {team} got {t} why {w} name.x0-x_text {(p.name.x0 - x0 - 9 * k) / k:.1f}k col {p.name.color}")
            if save:
                y = p.row.y
                a, b = x0, p.name.x1
                crop = rgb[y - k : y + 9 * k, a:b]
                mk = np.repeat(bm[y - k : y + 9 * k, a:b, None], 3, axis=2).astype(np.uint8) * 255
                im = np.concatenate([crop, mk], axis=0)
                s = max(1, 8 // k)
                Image.fromarray(im).resize((im.shape[1] * s, im.shape[0] * s), Image.NEAREST).save(OUT / f"{n[:40]}_{m}.png")
    print(dict(why))


if __name__ == "__main__":
    main()
