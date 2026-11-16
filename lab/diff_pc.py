"""diff_pc.py old.txt new.txt: images whose missing count changed"""

import ast
import re
import sys


def load(p: str) -> dict[str, int]:
    out = {}
    for line in open(p):
        m = re.match(r"(\S+)\s+k\d+ extra (\{.*?\}) missing (\{.*?\})$", line.strip())
        if m:
            out[m.group(1)] = sum(ast.literal_eval(m.group(3)).values())
    return out


a, b = load(sys.argv[1]), load(sys.argv[2])
for n in sorted(set(a) | set(b)):
    x, y = a.get(n, 0), b.get(n, 0)
    if x != y:
        print(f"{n:70s} {x:3d} -> {y:3d}")
