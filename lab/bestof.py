"""bestof.py A.json B.json: per-image oracle max and 'more answers' picker."""
import json
import sys

a = json.loads(open(sys.argv[1]).read())["images"]
b = json.loads(open(sys.argv[2]).read())["images"]
rows = orc = pick = pw = 0
for n in a:
    x, y = a[n], b[n]
    rows += len(x["correct"]) + len(x["wrong"]) + len(x["unknown"])
    orc += max(len(x["correct"]), len(y["correct"]))
    ans = lambda v: len(v["correct"]) + len(v["wrong"]) + len(v["npc"]) + len(v["extra"])
    p = x if ans(x) >= ans(y) else y
    pick += len(p["correct"])
    pw += len(p["wrong"]) + len(p["npc"]) + len(p["extra"])
print(f"rows {rows} oracle {100 * orc / rows:.1f} picker(more answers) {100 * pick / rows:.1f} wrong {pw}")
