import collections

from data import label, train_names

c = collections.Counter()
for n in train_names():
    lab = label(n)
    s = lab["setup"]
    key = (lab["source"], s["os"], s["client"], s["font"], s["gui_scale"])
    c[key] += 1
    print(n, len(lab["rows"]), len(lab["known"]), lab["in_game"], lab.get("tab_columns"))
for k, v in sorted(c.items(), key=str):
    print(v, k)
