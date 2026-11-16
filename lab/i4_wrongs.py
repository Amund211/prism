"""Print wrong / npc / extra rows of a results json. i4_wrongs.py NAME"""

import json
import sys
from pathlib import Path

d = json.loads((Path(__file__).parent / f"results/{sys.argv[1]}.json").read_text())
for n, o in d["images"].items():
    bad = {k: o[k] for k in ("wrong", "npc", "extra") if o[k]}
    if bad:
        print(n, bad)
