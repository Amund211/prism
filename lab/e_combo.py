"""e_combo.py: E2d combine rules on cached OCR (tags e2s5 = E2, e2c = E2c).
Re-cache e2c after changing e2c_rowband.read_lines."""

import json
from collections import Counter
from pathlib import Path

import e2d_union
from bench import outcome
from data import label
from e2c_rowband import match_all
from e_ocrcommon import match

R = Path(__file__).parent / "results"
a_res = json.loads((R / "ocr_e2s5.json").read_text())
c_res = json.loads((R / "ocr_e2c.json").read_text())

for veto in (False, True):
    e2d_union.VETO = veto
    c = Counter()
    for n in a_res:
        lab = label(n)
        known = list(lab["known"])
        a = match(a_res[n]["texts"], a_res[n]["teams"], known, 0.45, 0.1)
        m = match_all(c_res[n]["texts"], c_res[n]["teams"], known)
        for k, v in outcome(lab, e2d_union.combine(a, m)).items():
            c[k] += len(v)
    tot = c["correct"] + c["wrong"] + c["unknown"]
    bad = c["wrong"] + c["npc"] + c["extra"]
    print(f"veto {veto}: correct {100*c['correct']/tot:.1f} wrong {100*bad/tot:.2f} ({bad}) rows {tot}")
