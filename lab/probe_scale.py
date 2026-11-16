from data import image, label, train_names
from textmask import scale_votes

for n in train_names()[::6]:
    lab = label(n)
    v = scale_votes(image(n))
    print(lab["setup"]["gui_scale"], lab["setup"]["font"], {k: round(c / max(v[1], 1), 2) for k, c in v.items()})
