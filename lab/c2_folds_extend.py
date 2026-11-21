"""c2_folds_extend.py OLD.json OUT.json: old {image: fold} + the new train images.

A new image gets the old fold of its font pack (that fold's model never saw the
pack), else fold 0 (no fold model saw any real row of a new pack)."""

import json
import sys
from pathlib import Path

from data import label, train_names

old = json.loads(Path(sys.argv[1]).read_text())
pack_fold = {label(n)["setup"].get("font", "?"): f for n, f in old.items()}
out = {n: old.get(n, pack_fold.get(label(n)["setup"].get("font", "?"), 0)) for n in train_names()}
Path(sys.argv[2]).write_text(json.dumps(out, indent=0))
print("old", len(old), "new", len(out) - len(old), "per fold", [list(out.values()).count(f) for f in range(3)])
