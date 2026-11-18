"""C2: train a CRNN-CTC reader (i4 architecture, width option), seeded.
Usage: c2_train.py NAME DATA[,DATA2] FOLD EPOCHS [--width 1.0] [--seed 0] [--threads 4]
FOLD -1 = all fonts; else drop the font ids of results/i4/folds.json[FOLD].
Writes results/c2/NAME.onnx, NAME.pt, NAME.log.json. Needs: uv sync --group train"""

import argparse
import json
import pickle
import random
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn

from i4_synth import CHARS, H
from i4_train import batches, greedy

OUT = Path(__file__).parent / "results/c2"
FOLDS = Path(__file__).parent / "results/i4/folds.json"


def cbr(i, o, k=3, p=1):
    return [nn.Conv2d(i, o, k, padding=p, bias=False), nn.BatchNorm2d(o), nn.ReLU(inplace=True)]


def c1(i, o, d):
    return [nn.Conv1d(i, o, 3, padding=d, dilation=d, bias=False), nn.BatchNorm1d(o), nn.ReLU(inplace=True)]


class Net(nn.Module):
    """width 1.0 = the i4 net (16-48-64-64-96, 3 dilated 1-D convs)"""

    def __init__(self, width: float = 1.0, depth: int = 3) -> None:
        super().__init__()
        w = lambda c: int(round(c * width))  # noqa: E731
        self.cnn = nn.Sequential(
            *cbr(3, w(16)), nn.MaxPool2d(2, 2),
            *cbr(w(16), w(48)), nn.MaxPool2d((2, 1), (2, 1)),
            *cbr(w(48), w(64)), *cbr(w(64), w(64)),
            *cbr(w(64), w(96), (5, 1), 0),
        )
        self.seq = nn.Sequential(*[m for d in [1, 2, 4, 8][:depth] for m in c1(w(96), w(96), d)])
        self.out = nn.Conv1d(w(96), len(CHARS) + 1, 1)

    def forward(self, x):
        y = self.cnn(x).squeeze(2)
        return self.out(self.seq(y) + y)


def main() -> None:
    a = argparse.ArgumentParser()
    a.add_argument("name")
    a.add_argument("data")
    a.add_argument("fold", type=int)
    a.add_argument("epochs", type=int)
    a.add_argument("--width", type=float, default=1.0)
    a.add_argument("--depth", type=int, default=3)
    a.add_argument("--seed", type=int, default=0)
    a.add_argument("--threads", type=int, default=4)
    o = a.parse_args()
    torch.manual_seed(o.seed)
    random.seed(o.seed)
    torch.set_num_threads(o.threads)
    data = []
    for d in o.data.split(","):
        p = OUT / f"{d}.pkl" if d != "i4" else Path(__file__).parent / "results/i4/data.pkl"
        data += pickle.loads(p.read_bytes())
    if o.fold >= 0:
        drop = set(json.loads(FOLDS.read_text())[o.fold])
        data = [d for d in data if d[2] not in drop]
    rng = np.random.default_rng(o.seed)
    perm = rng.permutation(len(data))
    data = [data[i] for i in perm]
    val, data = data[:2000], data[2000:]
    net = Net(o.width, o.depth)
    params = sum(p.numel() for p in net.parameters())
    print(o.name, "params", params, "train", len(data), flush=True)
    steps = o.epochs * (len(data) // 64 + 1)
    opt = torch.optim.AdamW(net.parameters(), 2e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, 3e-3, total_steps=steps, pct_start=0.1)
    ctc = nn.CTCLoss(zero_infinity=True)
    t0 = time.time()
    log = []
    for ep in range(o.epochs):
        net.train()
        tot = n = 0
        for x, lab in batches(data, 64, rng):
            lp = net(x).log_softmax(1).permute(2, 0, 1)
            tgt = torch.tensor([c for l in lab for c in l])
            loss = ctc(lp, tgt, torch.full((x.shape[0],), lp.shape[0]), torch.tensor([len(l) for l in lab]))
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
            tot += float(loss)
            n += 1
        net.eval()
        ok = 0
        with torch.no_grad():
            for x, lab in batches(val, 100, np.random.default_rng(0)):
                lg = net(x).numpy()
                ok += sum(greedy(lg[i]) == "".join(CHARS[c - 1] for c in lab[i]) for i in range(len(lab)))
        log.append({"ep": ep, "loss": round(tot / n, 4), "val_exact": round(ok / len(val), 4), "s": round(time.time() - t0)})
        print(log[-1], flush=True)
    net.eval()
    OUT.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(net, (torch.rand(1, 3, H, 120),), str(OUT / f"{o.name}.onnx"), dynamo=False,
                      input_names=["x"], output_names=["y"], dynamic_axes={"x": {0: "b", 3: "w"}, "y": {0: "b", 2: "t"}})
    torch.save(net.state_dict(), OUT / f"{o.name}.pt")
    (OUT / f"{o.name}.log.json").write_text(json.dumps({"args": vars(o), "params": params, "log": log}, indent=1))
    print("saved", o.name, f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
