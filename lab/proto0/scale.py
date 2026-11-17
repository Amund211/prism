"""Make scaled copies of all samples: samples/720p/, samples/480p/.

Bilinear (with antialias), like a scaled window or a video. Same file
names, so labels.json applies. The short side is scaled to the target, so
portrait and multi-monitor captures get the same factor as 1080p.
"""

from pathlib import Path

from PIL import Image

from samples import SAMPLES
SIZES = {"720p": 720, "480p": 480}

for name, height in SIZES.items():
    out = SAMPLES / name
    out.mkdir(exist_ok=True)
    for f in sorted(SAMPLES.glob("*.png")):
        im = Image.open(f).convert("RGB")
        s = height / min(im.size)
        size = (round(im.width * s), round(im.height * s))
        im.resize(size, Image.BILINEAR).save(out / f.name)
    print(name, len(list(out.glob("*.png"))), "images")
