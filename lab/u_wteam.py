"""u_wteam.py: wrong-team rows of the union (tau .7) and open (X2) reads"""

import pickle
import sys

from data import label
from tbench import score
from u_union import UVAR, read

mode = sys.argv[1] if len(sys.argv) > 1 else "union"
cache = pickle.loads(UVAR.read_bytes())
for n, img in sorted(cache.items()):
    o = score(label(n), read(img, list(label(n)["known"]), mode, "g3", 0.7))
    if o["wteam"]:
        print(n, o["wteam"])
