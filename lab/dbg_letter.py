import sys

import numpy as np

from common import shade_of
from data import image

n, y, x0, x1, k = sys.argv[1], *map(int, sys.argv[2:6])
color = tuple(map(int, sys.argv[6].split(",")))
rgb = image(n)
band = rgb[y : y + 8 * k, x0:x1]
m = shade_of(band, color)
for row in m:
    print("".join("#" if v else "." for v in row))
