"""i2_wrongs.py <result name>: print wrong / npc / extra per image."""

import json
import sys
from pathlib import Path

d = json.loads((Path(__file__).parent / "results" / f"{sys.argv[1]}.json").read_text())
for n, o in sorted(d["images"].items()):
    bad = {k: o[k] for k in ("wrong", "npc", "extra") if o[k]}
    if bad:
        print(n.replace("screenshot-", ""), json.dumps(bad))
