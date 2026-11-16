import sys
import time

from PIL import Image, ImageDraw

from data import image, label, train_names
from rows import find_tab

SCRATCH = "/tmp/claude-1000/-home-amund-git-overlay/e8ae7acd-5312-49fd-afc3-562a24ca66d5/scratchpad"
names = sys.argv[1:] or train_names()
for n in names:
    lab = label(n)
    rgb = image(n)
    t = time.perf_counter()
    tab = find_tab(rgb)
    dt = time.perf_counter() - t
    gs = lab["setup"]["gui_scale"]
    nrows = len(lab["rows"]) + len(lab["npcs"])
    got = (tab.k, len(tab.rows)) if tab else None
    flag = "" if tab and tab.k == gs and len(tab.rows) >= nrows else "  <<<"
    print(f"{n:70s} gs{gs} rows{nrows:3d} got {got} {dt*1000:.0f}ms{flag}")
    if len(sys.argv) > 1 and tab:
        im = Image.fromarray(rgb)
        d = ImageDraw.Draw(im)
        for r in tab.rows:
            d.rectangle([r.x0, r.y, r.x1, r.y + 8 * r.k], outline=(255, 0, 255))
        x0 = min(r.x0 for r in tab.rows) - 50
        y0 = min(r.y for r in tab.rows) - 50
        x1 = max(r.x1 for r in tab.rows) + 50
        y1 = max(r.y for r in tab.rows) + 50 + 8 * tab.k
        im.crop((x0, y0, x1, y1)).save(f"{SCRATCH}/rows-{n}.png")
