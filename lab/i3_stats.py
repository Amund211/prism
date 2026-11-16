"""i3_stats.py: structure statistics from /tmp/claude-1000/i3_seq.json."""

import json
from collections import Counter, defaultdict

D = json.load(open("/tmp/claude-1000/i3_seq.json"))


def blocks(seq):
    out = []
    for t in seq:
        if not out or out[-1] != t:
            out.append(t)
    return out


def main():
    prec = Counter()
    contig = Counter()
    order_dn = Counter()
    order_ac = Counter()
    name_cmp = Counter()
    cols = Counter()
    sizes = defaultdict(Counter)
    for img, d in D.items():
        mode = d["mode"]
        tc = Counter(d["truth"].values())
        tc.pop(None, None)
        tc.pop("", None)
        if tc:
            sizes[mode][(max(tc.values()), len(set(tc.values())) == 1)] += 1
        rows = d["rows"]
        cols[len({r[0] for r in d["all"]})] += 1
        # team order: matched (true team) rows, down then across
        seq = [r[4] for r in sorted(rows, key=lambda r: (r[0], r[1]))]
        b = blocks(seq)
        contig["contig" if len(b) == len(set(b)) else "split"] += 1
        if len(b) != len(set(b)):
            contig_ex = (img, b)
        for i, a in enumerate(b):
            for c in b[i + 1:]:
                prec[(a, c)] += 1
        seq_ac = [r[4] for r in sorted(rows, key=lambda r: (r[1], r[0]))]
        order_dn[len(blocks(seq)) == len(set(seq))] += 1
        order_ac[len(blocks(seq_ac)) == len(set(seq_ac))] += 1
        # name order inside a team (adjacent rows, same col)
        srt = sorted(rows, key=lambda r: (r[0], r[1]))
        for x, y in zip(srt, srt[1:]):
            if x[4] == y[4]:
                a, c = x[3], y[3]
                name_cmp["cs_ok" if a < c else "cs_bad"] += 1
                name_cmp["ci_ok" if a.lower() < c.lower() else "ci_bad"] += 1
    print("columns found:", dict(cols))
    print("team contiguous (down-then-across):", dict(contig), "across-then-down contig:", dict(order_ac))
    teams = sorted({t for a, b in prec for t in (a, b)})
    print("precedence a before b (a row, b col):")
    print("        " + " ".join(f"{t[:5]:>5}" for t in teams))
    for a in teams:
        print(f"{a:>7} " + " ".join(f"{prec[(a, b)]:5d}" for b in teams))
    print("name order adjacent same team:", dict(name_cmp))
    print("team sizes per mode (max, all equal):")
    for m, c in sizes.items():
        print(" ", m, dict(c))
    print("example split:", contig_ex if contig["split"] else None)


if __name__ == "__main__":
    main()
