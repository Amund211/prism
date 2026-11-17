"""I4: train the CRNN-CTC row reader. Usage: i4_train.py NAME FOLD EPOCHS
FOLD -1 = all fonts; else drop the font ids of folds.json[FOLD].
Writes results/i4/NAME.onnx.

Needs torch, which is not in pyproject.toml (large; install it ad hoc:
`uv pip install torch`). The i4_* readers only need the .onnx files
(onnxruntime). results/ is gitignored, so on a fresh checkout run
i4_gen.py, then this script, before the i4_* benches."""

import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn

from i4_synth import CHARS, H

OUT = Path(__file__).parent / "results/i4"
torch.set_num_threads(4)


def cbr(i: int, o: int, k=3, p=1) -> list:
    return [nn.Conv2d(i, o, k, padding=p, bias=False), nn.BatchNorm2d(o), nn.ReLU(inplace=True)]


def c1(i: int, o: int, d: int) -> list:
    return [nn.Conv1d(i, o, 3, padding=d, dilation=d, bias=False), nn.BatchNorm1d(o), nn.ReLU(inplace=True)]


class Net(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.cnn = nn.Sequential(
            *cbr(3, 16), nn.MaxPool2d(2, 2),  # 10 x W/2
            *cbr(16, 48), nn.MaxPool2d((2, 1), (2, 1)),  # 5
            *cbr(48, 64), *cbr(64, 64),
            *cbr(64, 96, (5, 1), 0),  # 1
        )
        self.seq = nn.Sequential(*c1(96, 96, 1), *c1(96, 96, 2), *c1(96, 96, 4))
        self.out = nn.Conv1d(96, len(CHARS) + 1, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:  # x: B,3,H,W float 0..1
        y = self.cnn(x).squeeze(2)
        return self.out(self.seq(y) + y)  # B, C, T


def batches(data: list, bs: int, rng: np.random.Generator):
    idx = sorted(range(len(data)), key=lambda i: data[i][0].shape[1] + rng.random() * 30)
    chunks = [idx[i : i + bs] for i in range(0, len(idx), bs)]
    rng.shuffle(chunks)
    for ch in chunks:
        W = max(data[i][0].shape[1] for i in ch)
        x = np.stack([np.pad(data[i][0], ((0, 0), (0, W - data[i][0].shape[1]), (0, 0)), mode="edge") for i in ch])
        x = torch.from_numpy(x).permute(0, 3, 1, 2).float() / 255
        lab = [[CHARS.index(c) + 1 for c in data[i][1]] for i in ch]
        yield x, lab


def greedy(logits: np.ndarray) -> str:
    best = logits.argmax(0)
    out, prev = [], 0
    for b in best:
        if b != prev and b:
            out.append(CHARS[b - 1])
        prev = b
    return "".join(out)


def main() -> None:
    name, fold, epochs = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    data = pickle.loads((OUT / "data.pkl").read_bytes())
    if fold >= 0:
        drop = set(json.loads((OUT / "folds.json").read_text())[fold])
        data = [d for d in data if d[2] not in drop]
    rng = np.random.default_rng(0)
    val, data = data[:1000], data[1000:]
    net = Net()
    print(name, "params", sum(p.numel() for p in net.parameters()), "train", len(data), flush=True)
    steps = epochs * (len(data) // 64 + 1)
    opt = torch.optim.AdamW(net.parameters(), 2e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, 3e-3, total_steps=steps, pct_start=0.1)
    ctc = nn.CTCLoss(zero_infinity=True)
    t0 = time.time()
    for ep in range(epochs):
        net.train()
        tot = n = 0
        for x, lab in batches(data, 64, rng):
            lp = net(x).log_softmax(1).permute(2, 0, 1)  # T,B,C
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
            for x, lab in batches(val, 100, rng):
                lg = net(x).numpy()
                ok += sum(greedy(lg[i]) == "".join(CHARS[c - 1] for c in lab[i]) for i in range(len(lab)))
        print(f"ep {ep} loss {tot / n:.3f} val_exact {ok / len(val):.3f} t {time.time() - t0:.0f}s", flush=True)
    net.eval()
    torch.onnx.export(net, (torch.rand(1, 3, H, 120),), str(OUT / f"{name}.onnx"), dynamo=False,
                      input_names=["x"], output_names=["y"], dynamic_axes={"x": {0: "b", 3: "w"}, "y": {0: "b", 2: "t"}})
    torch.save(net.state_dict(), OUT / f"{name}.pt")
    print("saved", name, f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
