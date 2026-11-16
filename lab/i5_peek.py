"""i5: peek at labels / images of a group (train only)."""

import sys
from collections import Counter

from data import image, label, train_names

grp = sys.argv[1]
names = [n for n in train_names() if label(n)["setup"]["font"] == grp or grp in n]
print(len(names), "images")
n = names[0]
lab = label(n)
print(n, image(n).shape)
print({k: v for k, v in lab.items() if k != "rows"})
for r in lab["rows"][:4]:
    print(r)
print(Counter(label(m)["setup"]["font"] for m in train_names()))
