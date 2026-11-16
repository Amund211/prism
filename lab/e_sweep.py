"""e_sweep.py <tag>...: score cached OCR texts over match thresholds"""

import json
import sys
from collections import Counter
from pathlib import Path

from bench import outcome
from data import label
from e_ocrcommon import match

OUT = Path(__file__).parent / "results"

for tag in sys.argv[1:]:
    res = json.loads((OUT / f"ocr_{tag}.json").read_text())
    labs = {n: label(n) for n in res}
    for mc in (0.35, 0.45, 0.55, 0.65):
        for mg in (0.05, 0.1, 0.15, 0.25):
            c = Counter()
            for n, v in res.items():
                got = match(v["texts"], v["teams"], list(labs[n]["known"]), mc, mg)
                for kk, vv in outcome(labs[n], got).items():
                    c[kk] += len(vv)
            tot = c["correct"] + c["wrong"] + c["unknown"]
            bad = c["wrong"] + c["npc"] + c["extra"]
            print(f"{tag} max_cost {mc} margin {mg}: correct {100*c['correct']/tot:.1f} wrong {100*bad/tot:.2f} ({bad})")
