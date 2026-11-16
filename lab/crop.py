"""crop.py <name> x0 y0 x1 y1 [zoom] -> scratch png"""

import sys

from PIL import Image

from data import image

name, x0, y0, x1, y1 = sys.argv[1], *map(int, sys.argv[2:6])
zoom = int(sys.argv[6]) if len(sys.argv) > 6 else 1
im = Image.fromarray(image(name)[y0:y1, x0:x1])
im = im.resize((im.width * zoom, im.height * zoom), Image.NEAREST)
out = f"/tmp/claude-1000/-home-amund-git-overlay/e8ae7acd-5312-49fd-afc3-562a24ca66d5/scratchpad/{name}.png"
im.save(out)
print(out)
