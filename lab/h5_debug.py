"""h5_debug.py <image name> [module]: print layer lines and labels."""

import importlib
import sys

import cv2

import e2c_rowband as rb
from data import image, label

name = sys.argv[1]
mod = importlib.import_module(sys.argv[2] if len(sys.argv) > 2 else "h5_layer")
rgb = image(name)
lab = label(name)
print("labels", [(r["name"], r["team"]) for r in lab["rows"]])
bs = rb.bands(rgb)
print("bands", len(bs), bs[:3])
for t in mod.layer_lines(rgb):
    print(repr(t))
orig = mod.rec
n = [0]


def spy(img):  # type: ignore[no-untyped-def]
    n[0] += 1
    if n[0] <= 6:
        cv2.imwrite(f"/tmp/claude-1000/h5_{n[0]}.png", img)
    return orig(img)


mod.rec = spy
mod.layer_lines(rgb)
