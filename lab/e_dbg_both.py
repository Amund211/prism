import sys

import e2_rapidocr
import e2c_rowband
from data import image, label

n = sys.argv[1]
rgb = image(n)
known = list(label(n)["known"])
print("e2 ", e2_rapidocr.read_teams(rgb, known))
print("e2c", e2c_rowband.read_teams(rgb, known))
for line in e2c_rowband.read_lines(rgb):
    print(line)
