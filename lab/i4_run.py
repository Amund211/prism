"""I4 driver: dataset, then full model, then the leave-fold-out models."""

import subprocess
import sys

N, EP = sys.argv[1], sys.argv[2]
cmds = [["i4_gen.py", N], ["i4_train.py", "full", "-1", EP]]
cmds += [["i4_train.py", f"loo{i}", str(i), EP] for i in range(3)]
for c in cmds:
    print("run", c, flush=True)
    subprocess.run([sys.executable, *c], check=True)
