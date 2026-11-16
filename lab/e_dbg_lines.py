import importlib
import sys

from data import image, label

mod = importlib.import_module(sys.argv[1])
n = sys.argv[2]
print([(r["name"], r["team"]) for r in label(n)["rows"]])
for line in mod.read_lines(image(n)):
    print(line)
