"""Sanity: bank size, families, render a name, exclusions."""

import time

from g_bank import bank, excluded_for, ink_width, render

t = time.perf_counter()
b = bank()
print(len(b), "fonts", round(time.perf_counter() - t, 2), "s")
print("families", len({f.family for f in b}), "unknown fam", sum(f.family.startswith("N?") for f in b))
v = b[0]
m = render(v, "Skydeaf", 2)
print(m.shape, ink_width(v, "Skydeaf"))
for row in render(v, "Sky", 1):
    print("".join("#" if x else "." for x in row))
for sf in ["pack:tc02-hd-vanilla-16x", "pack:tc03-bombies", "pack:tc15-cell55-conquest", "pack:betterbedwars", "vanilla"]:
    ex = excluded_for(sf)
    print(sf, None if ex is None else len(ex))
