"""Debug one sample: rows found, candidates, and an annotated image.

usage: debug.py <sample.png> <out.png> [x0 y0 x1 y1]
"""

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tabteams as tt  # noqa: E402

from samples import SAMPLES  # noqa: E402

rgb = np.asarray(Image.open(SAMPLES / sys.argv[1]).convert("RGB"))
idx, s = tt.find_text(rgb)
labels, comps = tt.find_comps(idx, s)
words = tt.find_words(labels, comps, s)
rows = tt.find_rows(words, s)
print("scale", s, "text px", int((idx >= 0).sum()), "words", len(words), "rows", len(rows))

im = Image.fromarray(rgb).copy()
d = ImageDraw.Draw(im)
for w in words:
    for g in w.glyphs:
        d.rectangle((g.x0, w.y0, g.x1 - 1, w.y1 - 1), outline=(255, 0, 255))
    if len(w.glyphs) > 1:
        d.rectangle((w.x0 - 1, w.y0 - 1, w.x1, w.y1), outline=(0, 255, 255))

label = json.loads((SAMPLES / "labels.json").read_text())[sys.argv[1]]
known = [r["name"] for r in label["rows"]]
got = tt.match(rows, known)
seen = tt.solve(rows, known)
for i, r in enumerate(rows):
    d.rectangle(r.box, outline=(255, 128, 0), width=2)
    cands = [n for n in known if tt._pairs(r, n) is not None]
    print(r.team, r.box, "gids", r.name, cands, "best:", seen and seen[i], "->", got.get(i))
if len(sys.argv) > 3:
    im = im.crop(tuple(int(v) for v in sys.argv[3:7]))
    im = im.resize((im.width * 3, im.height * 3), Image.NEAREST)
im.save(sys.argv[2])
