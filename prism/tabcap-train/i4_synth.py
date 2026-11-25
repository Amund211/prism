"""I4: font render, random names and scene helpers for the synthetic rows."""

import math

import cv2
import numpy as np
from PIL import Image

from g_bank import BankFont, vanilla
from paths import resource_packs

CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_[]+ "
NAME_CHARS = CHARS[:63]
PALETTE = [
    0x000000,
    0x0000AA,
    0x00AA00,
    0x00AAAA,
    0xAA0000,
    0xAA00AA,
    0xFFAA00,
    0xAAAAAA,
    0x555555,
    0x5555FF,
    0x55FF55,
    0x55FFFF,
    0xFF5555,
    0xFF55FF,
    0xFFFF55,
    0xFFFFFF,
]
TEAM = [0xFF5555, 0x5555FF, 0x55FF55, 0xFFFF55, 0x55FFFF, 0xFFFFFF, 0xFF55FF, 0x555555]


# ---- soft font render (alpha + texture colour) ------------------------------

_RGBA: dict[str, np.ndarray] = {}


def _tex(f: BankFont) -> np.ndarray:
    t = _RGBA.get(f.fid)
    if t is None:
        p = (
            vanilla()
            if f.fid == "vanilla"
            else resource_packs() / "fonts" / f.fid / "ascii.png"
        )
        t = np.asarray(Image.open(p).convert("RGBA")).astype(np.float32) / 255
        _RGBA[f.fid] = t
    return t


def render_rgba(f: BankFont, text: str, k: int) -> np.ndarray:
    """Float 8k x W x 4 (texture rgb, alpha after the > 0.1 alpha test)"""
    tex = _tex(f)
    xs, X = [], 0.0
    for c in text:
        o = ord(c) if ord(c) < 256 else ord("?")
        xs.append((o, X))
        X += f.w[o]
    W = int(math.ceil(X * k)) + 2
    img = np.zeros((8 * k, W, 4), np.float32)
    v = (np.arange(8 * k) + 0.5) / k
    for o, X0 in xs:
        wq = f.w[o] - 1.01
        if wq <= 0:
            continue
        px = np.arange(math.floor(X0 * k), math.ceil((X0 + wq) * k))
        u = (px + 0.5) / k - X0
        keep = (u >= 0) & (u < wq) & (px < W)
        if not keep.any():
            continue
        tx = np.minimum((u[keep] * f.cw / 8).astype(int), f.cw - 1) + (o % 16) * f.cw
        ty = np.minimum((v * f.ch / 8).astype(int), f.ch - 1) + (o // 16) * f.ch
        g = tex[np.ix_(ty, tx)]
        g[..., 3] = np.where(g[..., 3] > 0.1, g[..., 3], 0)
        cols = px[keep]
        cur = img[:, cols]
        img[:, cols] = np.where(g[..., 3:] > cur[..., 3:], g, cur)
    return img


# ---- one synthetic sample ---------------------------------------------------


REAL_NAMES: list[str] | None = (
    None  # set by c2_gen "v3n": 70 % real names (Flashlight export)
)


def rand_name(rng: np.random.Generator) -> str:
    if REAL_NAMES is not None and rng.random() < 0.7:
        return REAL_NAMES[int(rng.integers(len(REAL_NAMES)))]
    n = int(rng.integers(3, 17))
    if rng.random() < 0.5:
        return "".join(rng.choice(list(NAME_CHARS), n))
    # word-like: letters, then maybe digits / underscore
    letters = "".join(rng.choice(list(NAME_CHARS[:52]), max(3, n - 3)))
    tail = "".join(rng.choice(list("0123456789_"), int(rng.integers(0, 4))))
    return (letters + tail)[:16]


def _rgb(c: int) -> np.ndarray:
    return np.array([(c >> 16) & 255, (c >> 8) & 255, c & 255], np.float32) / 255


def _scene(rng: np.random.Generator, h: int, w: int) -> np.ndarray:
    lo = rng.random((int(rng.integers(2, 6)), int(rng.integers(2, 12)), 3)).astype(
        np.float32
    )
    s = cv2.resize(lo, (w, h), interpolation=cv2.INTER_CUBIC)
    s += rng.normal(0, rng.uniform(0, 0.12), s.shape).astype(np.float32)
    if rng.random() < 0.3:  # blocky textures
        b = int(rng.integers(2, 9))
        t = rng.random(((h + b - 1) // b, (w + b - 1) // b, 3)).astype(np.float32)
        t = np.repeat(np.repeat(t, b, 0), b, 1)[:h, :w]
        s = 0.5 * s + 0.5 * t
    return np.clip(s, 0, 1)
