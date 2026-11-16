"""Upper bound: labeled team rows whose name is in known."""

from data import label, train_names

tot = ink = 0
for n in train_names():
    lab = label(n)
    known = set(lab["known"])
    for r in lab["rows"]:
        tot += 1
        ink += r["name"] in known or r["team"] is None
print(tot, ink, round(100 * ink / tot, 1))
