"""ping_dbg.py <name substr>: print all ping candidates for the images"""
import os
import sys

os.environ["P_DEBUG"] = "1"
import ping_grid  # noqa: E402
from data import image, train_names  # noqa: E402

for n in train_names():
    if sys.argv[1] in n:
        print(n)
        ping_grid.find_ping(image(n))
