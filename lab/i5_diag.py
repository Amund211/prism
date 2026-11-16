"""i5: per image, rows found vs labelled; why named rows have no team."""

import sys

import numpy as np
from PIL import Image

from common import parse
from data import image, label, train_names
from rowparse import nearest_team

pat = sys.argv[1]
save = "--save" in sys.argv
for n in train_names():
    if pat not in n:
        continue
    rgb = image(n)
    lab = label(n)
    tab, prows = parse(rgb)
    want = sum(1 for r in lab["rows"] if r["team"])
    named = [p for p in prows if p.name]
    print(f"{n} k{tab.k if tab else 0} label {want} prows {len(prows)} named {len(named)} "
          f"team {sum(1 for p in prows if p.team)} overlay {lab.get('overlay')}")
    for p in prows:
        if p.name and not p.team:
            print(f"   y{p.row.y} x{p.name.x0}-{p.name.x1} col {p.name.color} sh {p.name.shadow} "
                  f"near {nearest_team(p.name.color)} letter {p.letter is not None}")
    if save and tab:
        ys = [r.y for r in tab.rows]
        y0, y1 = max(0, min(ys) - 40 * tab.k), min(rgb.shape[0], max(ys) + 40 * tab.k)
        x0 = max(0, min(r.x0 for r in tab.rows) - 40 * tab.k)
        x1 = min(rgb.shape[1], max(r.x1 for r in tab.rows) + 40 * tab.k)
        crop = rgb[y0:y1, x0:x1].copy()
        for r in tab.rows:
            crop[max(0, r.y - y0), max(0, r.x0 - x0):r.x1 - x0] = (255, 0, 255)
        Image.fromarray(crop).save(f"/tmp/claude-1000/i5_{n[-40:]}.png")
        print("   crop", y0, y1, x0, x1)
