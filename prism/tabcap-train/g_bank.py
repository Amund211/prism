"""Font bank: the 100 stored pack fonts + vanilla, with 1.8.9 FontRenderer
advance widths (rules from resource_packs/tools/synth_tabs.py, checked there
against real captures). Two modes per HD font: vanilla int widths, OptiFine
float widths (+ ascii.properties widths)."""

import json
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import numpy as np
from PIL import Image

from paths import resource_packs


def vanilla() -> Path:
    return resource_packs() / "vanilla/1.8.9/assets/minecraft/textures/font/ascii.png"


@dataclass
class BankFont:
    fid: str  # font_id, or "vanilla"
    family: str  # N label from the survey (near-identical fonts share it)
    mode: str  # "vanilla" | "optifine"
    a: np.ndarray  # alpha, float
    cw: int
    ch: int
    w: list[float]  # advance per char, GUI px

    @property
    def key(self) -> str:
        return f"{self.fid}/{self.mode}"


def _families() -> dict[str, str]:
    out = {}
    for line in (resource_packs() / "README.md").read_text().splitlines():
        m = re.match(r"\| F\d+[^|]*\| (N\d+) \| `([0-9a-f]{12})`", line)
        if m:
            out[m.group(2)] = m.group(1)
    return out


def _make(fid: str, family: str, path: Path, mode: str, props: dict) -> BankFont:
    a = np.asarray(Image.open(path).convert("RGBA")).astype(np.float32)[..., 3] / 255
    cw, ch = a.shape[1] // 16, a.shape[0] // 16
    w = []
    for o in range(256):
        cell = a[(o // 16) * ch : (o // 16 + 1) * ch, (o % 16) * cw : (o % 16 + 1) * cw]
        cols = np.flatnonzero((cell > 0).any(0))
        l1 = int(cols.max()) + 1 if len(cols) else 0
        if o == 32 and mode == "optifine" and cw > 8:
            w.append((cw * 5 // 16 + 1) * 8 / cw)
        elif o == 32:
            w.append(4.0)
        elif mode == "optifine" and cw > 8:
            w.append(l1 * 8 / cw + 1)
        else:
            w.append(float(int(0.5 + l1 * 8 / cw) + 1))
    if mode == "optifine":
        for key, v in props.items():
            if key.startswith("width.") and key[6:].isdigit() and int(key[6:]) < 256:
                w[int(key[6:])] = float(v)
    return BankFont(fid, family, mode, a, cw, ch, w)


@cache
def bank() -> list[BankFont]:
    fam = _families()
    out = [_make("vanilla", "N1", vanilla(), "vanilla", {})]
    for d in sorted((resource_packs() / "fonts").iterdir()):
        p = d / "ascii.png"
        if not p.exists():
            continue
        pj = d / "ascii.properties.json"
        props = json.loads(pj.read_text()) if pj.exists() else {}
        f = _make(d.name, fam.get(d.name, "N?" + d.name), p, "vanilla", props)
        out.append(f)
        if f.cw > 8 or props:
            out.append(_make(d.name, f.family, p, "optifine", props))
    return out
