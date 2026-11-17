"""tl_ocrdiff.py: CRNN vs RapidOCR reads vs label, for regions where the
label name is near one of them; counts which reader is right."""

import pickle
from collections import Counter
from pathlib import Path

from rapidfuzz.distance import Levenshtein

from data import label

cache = pickle.loads((Path(__file__).parent / "results/tl/cache_loo_ocr.pkl").read_bytes())
cnt = Counter()
ex = []
for name, img in sorted(cache.items()):
    names = [r["name"] for r in label(name)["rows"]]
    for r in img["regions"]:
        c, o = r["name"][0].replace(" ", ""), r["ocr"] or ""
        best = min(names, key=lambda n: min(Levenshtein.distance(n, c), Levenshtein.distance(n, o)), default=None)
        if best is None or min(Levenshtein.distance(best, c), Levenshtein.distance(best, o)) > 3:
            continue
        key = ("crnn" if c == best else "-") + "/" + ("ocr" if o == best else "-")
        cnt[key] += 1
        if o != best and len(ex) < 400:
            ex.append(f"{best} | crnn {c} | ocr {o}")
print(cnt)
for e in ex[::8]:
    print(" ", e)
