"""e_sweep2.py <module> <tag>: sweep thresholds of module.match_lines on cached lines"""

import importlib
import json
import sys
from collections import Counter
from pathlib import Path

from bench import outcome
from data import label

mod = importlib.import_module(sys.argv[1])
res = json.loads((Path(__file__).parent / "results" / f"ocr_{sys.argv[2]}.json").read_text())
labs = {n: label(n) for n in res}
for mc in (0.2, 0.3, 0.4, 0.5):
    for mg in (0.05, 0.1, 0.15, 0.25):
        c = Counter()
        for n, v in res.items():
            got = mod.match_lines(v["texts"], v["teams"], list(labs[n]["known"]), mc, mg)
            for kk, vv in outcome(labs[n], got).items():
                c[kk] += len(vv)
        tot = c["correct"] + c["wrong"] + c["unknown"]
        bad = c["wrong"] + c["npc"] + c["extra"]
        print(f"max_cost {mc} margin {mg}: correct {100*c['correct']/tot:.1f} wrong {100*bad/tot:.2f} ({bad})")
