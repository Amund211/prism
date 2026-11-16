"""e_dbg.py <module> <name>: OCR text per row and best known match"""

import importlib
import sys

from common import parse
from data import image, label
from e_ocrcommon import name_crop, sim

mod = importlib.import_module(sys.argv[1])
n = sys.argv[2]
lab = label(n)
tab, prows = parse(image(n))
for p in prows:
    if p.name is None:
        continue
    t = mod.ocr(name_crop(p))
    best = sorted(lab["known"], key=lambda k: -sim(t, k))[:2]
    print(p.row.y, p.team, repr(t), [(b, round(sim(t, b), 2)) for b in best])
