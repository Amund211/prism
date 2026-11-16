import sys
from collections import Counter

from data import image
from rowparse import words
from rows import find_tab

for n in sys.argv[1:]:
    rgb = image(n)
    tab = find_tab(rgb)
    k = tab.k
    c: Counter = Counter()
    for r in tab.rows:
        ws = words(rgb, tab.mask, r, gap=1000)  # one word per row: all spans
        for w in ws:
            sp = w.spans
            for (a, b), (p, q) in zip(sp, sp[1:]):
                c[round((p - b) / k, 1)] += 1
    print(n, k, sorted(c.items()))
