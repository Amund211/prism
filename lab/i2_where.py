"""i2_where.py <image substr> <name>: save a crop around the best spot hit."""

import sys

import cv2
import numpy as np

import i2_spot as s
from data import image, label, train_names
from g_bank import bank

n = next(n for n in train_names() if sys.argv[1] in n)
rgb = image(n)
known = list(label(n)["known"])
print(n, label(n)["npcs"], [r for r in label(n)["rows"] if r["name"] == sys.argv[2]])
k, box = s.tab_box(rgb)
sm, col, shd = s.font_px(rgb, k, box)
fonts = s.pick_fonts(sm, known)
print("k", k, "box", box, "fonts", [bank()[f].key for f in fonts])
j = known.index(sys.argv[2])
r, t = s.scores(sm, fonts[:1], [known[j]])[fonts[0], 0]
for v, y, x in s.peaks(r, 3, t.shape[1]):
    print("peak", round(v, 3), y, x, s.team_at(col, shd, t, y, x), s.letter_at(sm, bank()[fonts[0]], y, x, t.shape[0]))
_, _, _, (x, y) = cv2.minMaxLoc(r)
Y, X = box[0] + y * k, box[2] + x * k
crop = rgb[max(0, Y - 30 * k) : Y + 40 * k, max(0, X - 40 * k) : X + 150 * k]
cv2.imwrite("/tmp/claude-1000/i2_where.png", cv2.cvtColor(np.ascontiguousarray(crop), cv2.COLOR_RGB2BGR))
