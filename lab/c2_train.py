"""C2: train a CRNN-CTC reader (i4 architecture, width option), seeded.
Usage: c2_train.py NAME DATA[,DATA2] FOLD EPOCHS [--width 1.0] [--seed 0] [--threads 4] [--tokens]
FOLD -1 = all fonts; else drop the font ids of results/i4/folds.json[FOLD].
Writes results/c2/NAME.onnx, NAME.pt, NAME.log.json. Needs: uv sync --group train"""

import argparse
import json
import pickle
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn

from c2_synth import CHARS_T
from i4_synth import CHARS, H

OUT = Path(__file__).parent / "results/c2"
FOLDS = Path(__file__).parent / "results/i4/folds.json"


def cbr(i, o, k=3, p=1):
    return [nn.Conv2d(i, o, k, padding=p, bias=False), nn.BatchNorm2d(o), nn.ReLU(inplace=True)]


def c1(i, o, d):
    return [nn.Conv1d(i, o, 3, padding=d, dilation=d, bias=False), nn.BatchNorm1d(o), nn.ReLU(inplace=True)]


class Block(nn.Module):
    """pre-norm transformer block; own attention so the ONNX export keeps a dynamic width"""

    def __init__(self, d: int, heads: int = 4) -> None:
        super().__init__()
        self.h, self.dh = heads, d // heads
        self.n1, self.n2 = nn.LayerNorm(d), nn.LayerNorm(d)
        self.qkv, self.proj = nn.Linear(d, 3 * d), nn.Linear(d, d)
        self.ff = nn.Sequential(nn.Linear(d, 2 * d), nn.GELU(), nn.Linear(2 * d, d))
        self.drop = nn.Dropout(0.1)

    def forward(self, x):  # B x T x d
        q, k, v = self.qkv(self.n1(x)).chunk(3, dim=-1)
        q, k, v = (t.reshape(x.shape[0], -1, self.h, self.dh).transpose(1, 2) for t in (q, k, v))
        a = torch.softmax(q @ k.transpose(-1, -2) / self.dh**0.5, dim=-1) @ v
        x = x + self.drop(self.proj(a.transpose(1, 2).reshape(x.shape[0], -1, self.h * self.dh)))
        return x + self.drop(self.ff(self.n2(x)))


class Net(nn.Module):
    """width 1.0 = the i4 net (16-48-64-64-96, 3 dilated 1-D convs)"""

    def __init__(self, width: float = 1.0, depth: int = 3, n_chars: int = len(CHARS), tf: int = 0) -> None:
        super().__init__()
        self.tf = None
        if tf:  # SVTR-like: global self-attention over the column features, after the convs
            d = int(round(96 * width))
            self.tf = nn.Sequential(*[Block(d) for _ in range(tf)])
            pos = torch.arange(1024)[:, None] / torch.pow(10000, torch.arange(0, d, 2)[None] / d)
            pe = torch.zeros(1024, d)
            pe[:, 0::2], pe[:, 1::2] = torch.sin(pos), torch.cos(pos)
            self.register_buffer("pe", pe.T[None], persistent=False)
        w = lambda c: int(round(c * width))  # noqa: E731
        self.cnn = nn.Sequential(
            *cbr(3, w(16)), nn.MaxPool2d(2, 2),
            *cbr(w(16), w(48)), nn.MaxPool2d((2, 1), (2, 1)),
            *cbr(w(48), w(64)), *cbr(w(64), w(64)),
            *cbr(w(64), w(96), (5, 1), 0),
        )
        self.seq = nn.Sequential(*[m for d in [1, 2, 4, 8][:depth] for m in c1(w(96), w(96), d)])
        self.out = nn.Conv1d(w(96), n_chars + 1, 1)

    def forward(self, x):
        y = self.cnn(x).squeeze(2)
        y = self.seq(y) + y
        if self.tf is not None:
            y = self.tf((y + self.pe[:, :, : y.shape[2]]).transpose(1, 2)).transpose(1, 2)
        return self.out(y)


def batches(data: list, bs: int, rng: np.random.Generator, chars: str):
    """as i4_train.batches, with the charset as an argument"""
    idx = sorted(range(len(data)), key=lambda i: data[i][0].shape[1] + rng.random() * 30)
    chunks = [idx[i : i + bs] for i in range(0, len(idx), bs)]
    rng.shuffle(chunks)
    for ch in chunks:
        W = max(data[i][0].shape[1] for i in ch)
        x = np.stack([np.pad(data[i][0], ((0, 0), (0, W - data[i][0].shape[1]), (0, 0)), mode="edge") for i in ch])
        x = torch.from_numpy(x).permute(0, 3, 1, 2).float() / 255
        lab = [[chars.index(c) + 1 for c in data[i][1]] for i in ch]
        yield x, lab


def greedy(logits: np.ndarray, chars: str) -> str:
    best = logits.argmax(0)
    out, prev = [], 0
    for b in best:
        if b != prev and b:
            out.append(chars[b - 1])
        prev = b
    return "".join(out)


def exact(net, samples, chars) -> float:
    ok = 0
    with torch.no_grad():
        for x, lab in batches(samples, 100, np.random.default_rng(0), chars):
            lg = net(x).numpy()
            ok += sum(greedy(lg[i], chars) == "".join(chars[c - 1] for c in lab[i]) for i in range(len(lab)))
    return round(ok / len(samples), 4)


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
    a.add_argument("--limit", type=int, default=0, help="use only the first N train samples")
    a.add_argument("--stop-after", type=int, default=0, help="test only: exit after this epoch")
    a.add_argument("--tokens", action="store_true", help="charset with team tokens (c2_synth.CHARS_T)")
    a.add_argument("--tf", type=int, default=0, help="transformer layers after the convs (0 = CRNN)")
    a.add_argument("--init", default="", help="fine-tune: start from results/c2/INIT.pt")
    a.add_argument("--lr", type=float, default=3e-3, help="OneCycle max lr")
    a.add_argument("--extra", default="", help="NAME:REP - add results/c2/NAME.pkl REP times, after --limit")
    o = a.parse_args()
    if not o.init:  # keep the run identity (checkpoint args) of runs from before these flags
        del o.init
    if o.lr == 3e-3:
        del o.lr
    if not o.extra:
        del o.extra
    chars = CHARS_T if o.tokens else CHARS
    stop_after = o.stop_after
    del o.stop_after  # not part of the run identity
    torch.manual_seed(o.seed)
    random.seed(o.seed)
    torch.set_num_threads(o.threads)
    drop = set(json.loads(FOLDS.read_text())[o.fold]) if o.fold >= 0 else set()

    def load(d):
        p = OUT / f"{d}.pkl" if d != "i4" else Path(__file__).parent / "results/i4/data.pkl"
        return [s for s in pickle.loads(p.read_bytes()) if s[2] not in drop]

    # val comes from the first set only, so runs with extra data or --limit share it
    names = o.data.split(",")
    data = load(names[0])
    rng = np.random.default_rng(o.seed)
    perm = rng.permutation(len(data))
    data = [data[i] for i in perm]
    val, data = data[:2000], data[2000:]
    for d in names[1:]:
        data += load(d)
    if o.limit:
        data = data[: o.limit]
    seen = data[:2000]
    if getattr(o, "extra", ""):
        en, rep = o.extra.split(":")
        data += pickle.loads((OUT / f"{en}.pkl").read_bytes()) * int(rep)
    net = Net(o.width, o.depth, len(chars), o.tf)
    if getattr(o, "init", ""):
        net.load_state_dict(torch.load(OUT / f"{o.init}.pt"))
    params = sum(p.numel() for p in net.parameters())
    print(o.name, "params", params, "train", len(data), flush=True)
    steps = o.epochs * (len(data) // 64 + 1)
    opt = torch.optim.AdamW(net.parameters(), 2e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, getattr(o, "lr", 3e-3), total_steps=steps, pct_start=0.1)
    ctc = nn.CTCLoss(zero_infinity=True)
    t0 = time.time()
    log = []
    # per-epoch checkpoint with all state (net, optimizer, schedule, RNGs), so a resume continues the same run
    ck_path = OUT / f"{o.name}.ckpt"
    start = 0
    if ck_path.exists():
        ck = torch.load(ck_path, weights_only=False)
        if ck["args"] != vars(o):
            sys.exit(f"{ck_path} has other args: {ck['args']}")
        net.load_state_dict(ck["net"])
        opt.load_state_dict(ck["opt"])
        sched.load_state_dict(ck["sched"])
        rng.bit_generator.state = ck["np_rng"]
        torch.set_rng_state(ck["torch_rng"])
        random.setstate(ck["py_rng"])
        log, start = ck["log"], ck["log"][-1]["ep"] + 1
        t0 -= log[-1]["s"]
        print("resumed at epoch", start, flush=True)
    for ep in range(start, o.epochs):
        net.train()
        tot = n = 0
        for x, lab in batches(data, 64, rng, chars):
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
        log.append({"ep": ep, "loss": round(tot / n, 4), "val_exact": exact(net, val, chars),
                    "train_exact": exact(net, seen, chars), "s": round(time.time() - t0)})
        print(log[-1], flush=True)
        ck = {"args": vars(o), "net": net.state_dict(), "opt": opt.state_dict(), "sched": sched.state_dict(),
              "np_rng": rng.bit_generator.state, "torch_rng": torch.get_rng_state(), "py_rng": random.getstate(),
              "log": log}
        torch.save(ck, ck_path.with_suffix(".tmp"))
        ck_path.with_suffix(".tmp").replace(ck_path)
        if stop_after and ep + 1 == stop_after:
            sys.exit(f"stopped after epoch {ep + 1} (checkpoint kept)")
    net.eval()
    torch.onnx.export(net, (torch.rand(1, 3, H, 120),), str(OUT / f"{o.name}.onnx"), dynamo=False,
                      input_names=["x"], output_names=["y"], dynamic_axes={"x": {0: "b", 3: "w"}, "y": {0: "b", 2: "t"}})
    torch.save(net.state_dict(), OUT / f"{o.name}.pt")
    (OUT / f"{o.name}.log.json").write_text(json.dumps({"args": vars(o), "params": params, "log": log}, indent=1))
    ck_path.unlink()
    print("saved", o.name, f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
