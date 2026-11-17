"""Debug algorithm B on one sample: rows, best names by score.

usage: debug_b.py <res: 1080p|720p|480p> <sample.png> [out.png]
"""

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tabsoft as tb  # noqa: E402

from samples import SAMPLES  # noqa: E402
d = SAMPLES if sys.argv[1] == "1080p" else SAMPLES / sys.argv[1]
rgb = np.asarray(Image.open(d / sys.argv[2]).convert("RGB"))
label = json.loads((SAMPLES / "labels.json").read_text())[sys.argv[2]]
names = [r["name"] for r in label["rows"] if not r.get("npc")]
truth = {r["name"]: r["team"] for r in label["rows"]}

cls = tb.classify(rgb)
for l, n in tb._pairs(tb.segments(cls, 1)):
    print(f"pair {tb.TEAM_NAMES[l.color]:7} y{l.y0} x{n.x0}-{n.x1} letter {tb.letter_score(cls, l):.2f}")
rows = tb.find_rows(rgb)
print(len(rows), "rows")
for r in sorted(rows, key=lambda r: r.cap):
    sc = sorted(((tb.score(r, n), n) for n in names), reverse=True)[:3]
    print(
        f"{r.team:7} x{r.x0}-{r.x1} cap{r.cap} base{r.base}",
        " ".join(f"{n}({truth[n]}):{s:.1f}" for s, n in sc),
    )
print("result", tb.match(rows, names))
if len(sys.argv) > 3:
    im = Image.fromarray(rgb).copy()
    dr = ImageDraw.Draw(im)
    for r in rows:
        dr.rectangle((r.x0, r.cap, r.x1, r.base), outline=(255, 128, 0))
    im.save(sys.argv[3])
