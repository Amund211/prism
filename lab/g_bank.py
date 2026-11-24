"""Font bank: the 100 stored pack fonts + vanilla, rendered like the 1.8.9
FontRenderer (rules from resource_packs/tools/synth_tabs.py, checked there
against real captures). Two modes per HD font: vanilla int widths, OptiFine
float widths (+ ascii.properties widths)."""

import json
import math
import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

import numpy as np
from PIL import Image

from front_regions import NameRegion, name_region  # noqa: F401  (re-export for lab callers)

RP = Path.home() / "git/overlay/resource_packs"
VANILLA = RP / "vanilla/1.8.9/assets/minecraft/textures/font/ascii.png"
ALPHA = 0.5  # ink if alpha > this (AA fonts: faint edges are not in the word mask)


@dataclass
class BankFont:
    fid: str  # font_id, or "vanilla"
    family: str  # N label from the survey (near-identical fonts share it)
    mode: str  # "vanilla" | "optifine"
    a: np.ndarray  # alpha, float
    cw: int
    ch: int
    w: list[float]  # advance per char, GUI px
    ink: list[tuple[float, float]] = field(default_factory=list)  # ink left/right per char, GUI px
    glyphs: dict = field(default_factory=dict)  # (o, k, frac) -> bool array

    @property
    def key(self) -> str:
        return f"{self.fid}/{self.mode}"


def _families() -> dict[str, str]:
    out = {}
    for line in (RP / "README.md").read_text().splitlines():
        m = re.match(r"\| F\d+[^|]*\| (N\d+) \| `([0-9a-f]{12})`", line)
        if m:
            out[m.group(2)] = m.group(1)
    return out


def _make(fid: str, family: str, path: Path, mode: str, props: dict) -> BankFont:
    a = np.asarray(Image.open(path).convert("RGBA")).astype(np.float32)[..., 3] / 255
    cw, ch = a.shape[1] // 16, a.shape[0] // 16
    w, ink = [], []
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
        strong = np.flatnonzero((cell > ALPHA).any(0))
        ink.append((strong.min() * 8 / cw, (strong.max() + 1) * 8 / cw) if len(strong) else (0.0, 0.0))
    if mode == "optifine":
        for key, v in props.items():
            if key.startswith("width.") and key[6:].isdigit() and int(key[6:]) < 256:
                w[int(key[6:])] = float(v)
    return BankFont(fid, family, mode, a, cw, ch, w, ink)


@cache
def bank() -> list[BankFont]:
    fam = _families()
    out = [_make("vanilla", "N1", VANILLA, "vanilla", {})]
    for d in sorted((RP / "fonts").iterdir()):
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


def _glyph(f: BankFont, o: int, k: int, frac: float) -> np.ndarray:
    """Pixels of char o drawn at pixel offset frac (0..1) from an int pixel x"""
    key = (o, k, frac)
    g = f.glyphs.get(key)
    if g is not None:
        return g
    wq = f.w[o] - 1.01
    if wq <= 0:
        g = np.zeros((8 * k, 0), bool)
    else:
        X = frac / k
        px = np.arange(math.floor(X * k), math.ceil((X + wq) * k))
        u = (px + 0.5) / k - X
        keep = (u >= 0) & (u < wq)
        u = u[keep]
        v = (np.arange(8 * k) + 0.5) / k
        tx = np.minimum((u * f.cw / 8).astype(int), f.cw - 1) + (o % 16) * f.cw
        ty = np.minimum((v * f.ch / 8).astype(int), f.ch - 1) + (o // 16) * f.ch
        g = np.zeros((8 * k, int(px[keep].max()) + 1 if keep.any() else 0), bool)
        if keep.any():
            g[:, px[keep]] = f.a[np.ix_(ty, tx)] > ALPHA
    f.glyphs[key] = g
    return g


def render(f: BankFont, text: str, k: int) -> np.ndarray:
    """Bool mask (8k x W) of the text, leading / trailing blank columns cut"""
    xs = []
    X = 0.0
    for c in text:
        o = ord(c) if ord(c) < 256 else ord("?")
        xs.append((o, X))
        X += f.w[o]
    W = int(math.ceil(X * k)) + 2
    img = np.zeros((8 * k, W), bool)
    for o, X in xs:
        x = X * k
        xi = int(math.floor(x))
        g = _glyph(f, o, k, round(x - xi, 2))
        img[:, xi : xi + g.shape[1]] |= g
    cols = np.flatnonzero(img.any(0))
    return img[:, cols[0] : cols[-1] + 1] if len(cols) else img[:, :0]


def ink_width(f: BankFont, text: str) -> float:
    """Ink width in GUI px (cheap; no render)"""
    X = 0.0
    first = last = None
    for c in text:
        o = ord(c) if ord(c) < 256 else ord("?")
        lo, hi = f.ink[o]
        if hi > lo:
            first = X + lo if first is None else first
            last = X + hi
        X += f.w[o]
    return (last - first) if first is not None else 0.0


# ---- name regions in the image -------------------------------------------



def iou(a: np.ndarray, t: np.ndarray, shifts: int = 1) -> float:
    """Best IoU of a and t over +-shifts px offsets, after a vertical shift
    from the row-profile correlation (fonts differ in where glyphs sit in
    the cell; a few pixels may sit outside the image band)"""
    pa, pt = a.sum(1).astype(float), t.sum(1).astype(float)
    if not pa.any() or not pt.any():
        return 0.0
    h = a.shape[0]
    corr = np.correlate(pa, pt, mode="full")  # index h-1 = no shift
    dy0 = int(np.argmax(corr)) - (len(pt) - 1)  # a row i ~ t row i - dy0
    if dy0:
        tt = np.zeros_like(t)
        if dy0 > 0:
            tt[dy0:] = t[: h - dy0]
        else:
            tt[:dy0] = t[-dy0:]
        t = tt
    W = max(a.shape[1], t.shape[1]) + 2 * shifts
    A = np.zeros((h + 2 * shifts, W), bool)
    A[shifts : shifts + h, shifts : shifts + a.shape[1]] = a
    sa = int(a.sum())
    st = int(t.sum())
    best = 0.0
    for dy in range(2 * shifts + 1):
        for dx in range(2 * shifts + 1):
            inter = int(A[dy : dy + h, dx : dx + t.shape[1]][: t.shape[0]].__and__(t).sum())
            u = sa + st - inter
            if u and inter / u > best:
                best = inter / u
    return best


# ---- leave-own-font-out support (bench only) --------------------------------


@cache
def _pack_fonts() -> dict[str, set[str]]:
    """setup.font -> font ids of that test pack (with and without OptiFine)"""
    man = json.loads((RP / "test_set/manifest.json").read_text())
    out: dict[str, set[str]] = {}
    for case in man:
        ids = {
            case[m]["font_id"]
            for m in ("font_without_optifine", "font_with_optifine")
            if isinstance(case.get(m), dict) and case[m].get("font_id")
        }
        out[case["setup_font"]] = ids
    out["pack:bombies"] = out.get("pack:tc03-bombies", set())  # same Bombies family (N4)
    return out


def excluded_for(setup_font: str | None) -> set[str] | None:
    """Font ids (whole family) to drop for this image; None = unknown pack"""
    if not setup_font or setup_font == "vanilla":
        return set()
    ids = _pack_fonts().get(setup_font)
    if ids is None:
        return None
    fams = {f.family for f in bank() if f.fid in ids}
    return {f.fid for f in bank() if f.fid in ids or f.family in fams} - {"vanilla"}
