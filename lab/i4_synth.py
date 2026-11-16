"""I4: synthetic tab-row images for a small CRNN text reader, and the crop
normalisation shared by training and inference."""

import math

import cv2
import numpy as np
from PIL import Image

from g_bank import RP, VANILLA, BankFont, bank

H = 20  # model input height: rows y-k .. y+9k at 2 px per GUI px
CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_[]+ "
NAME_CHARS = CHARS[:63]
PALETTE = [0x000000, 0x0000AA, 0x00AA00, 0x00AAAA, 0xAA0000, 0xAA00AA, 0xFFAA00, 0xAAAAAA,
           0x555555, 0x5555FF, 0x55FF55, 0x55FFFF, 0xFF5555, 0xFF55FF, 0xFFFF55, 0xFFFFFF]
TEAM = [0xFF5555, 0x5555FF, 0x55FF55, 0xFFFF55, 0x55FFFF, 0xFFFFFF, 0xFF55FF, 0x555555]


def norm_crop(rgb: np.ndarray, y: int, x0: int, x1: int, k: int) -> np.ndarray:
    """Row band (y = top of glyph area) -> uint8 H x W x 3 at 2 px per GUI px"""
    ya, yb = y - k, y + 9 * k
    xa, xb = max(0, x0 - 2 * k), min(rgb.shape[1], x1 + 2 * k)
    band = np.zeros((yb - ya, xb - xa, 3), np.uint8)
    sa, sb = max(0, ya), min(rgb.shape[0], yb)
    band[sa - ya : sb - ya] = rgb[sa:sb, xa:xb]
    w = max(4, round((xb - xa) * 2 / k))
    interp = cv2.INTER_AREA if k > 2 else cv2.INTER_NEAREST
    return cv2.resize(band, (w, H), interpolation=interp)


# ---- soft font render (alpha + texture colour) ------------------------------

_RGBA: dict[str, np.ndarray] = {}


def _tex(f: BankFont) -> np.ndarray:
    t = _RGBA.get(f.fid)
    if t is None:
        p = VANILLA if f.fid == "vanilla" else RP / "fonts" / f.fid / "ascii.png"
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


def rand_name(rng: np.random.Generator) -> str:
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
    lo = rng.random((int(rng.integers(2, 6)), int(rng.integers(2, 12)), 3)).astype(np.float32)
    s = cv2.resize(lo, (w, h), interpolation=cv2.INTER_CUBIC)
    s += rng.normal(0, rng.uniform(0, 0.12), s.shape).astype(np.float32)
    if rng.random() < 0.3:  # blocky textures
        b = int(rng.integers(2, 9))
        t = rng.random(((h + b - 1) // b, (w + b - 1) // b, 3)).astype(np.float32)
        t = np.repeat(np.repeat(t, b, 0), b, 1)[:h, :w]
        s = 0.5 * s + 0.5 * t
    return np.clip(s, 0, 1)


def sample(rng: np.random.Generator, f: BankFont) -> tuple[np.ndarray, str]:
    k = int(rng.choice([1, 2, 2, 3, 3, 4]))
    text = rand_name(rng)
    if rng.random() < 0.08:
        text = "[" + "".join(rng.choice(list("ABCDEFGHIJKLMNOPQRSTUVWXYZ+"), int(rng.integers(1, 5)))) + "] " + text
    g = render_rgba(f, text, k)
    cols = np.flatnonzero(g[..., 3].max(0) > 0)
    if len(cols) == 0:
        text, g = "aaa", render_rgba(f, "aaa", k)
        cols = np.flatnonzero(g[..., 3].max(0) > 0)
    g = g[:, cols[0] : cols[-1] + 1]
    pad = 6 * k
    Hc, Wc = 12 * k, g.shape[1] + 2 * pad
    y0 = 2 * k  # glyph top in canvas
    img = _scene(rng, Hc, Wc)
    img = img * (1 - 0.5) + 0  # tab panel: black, alpha 0x80
    if rng.random() < 0.85:
        img = img * (1 - 0.125) + 0.125  # row cell: white, alpha 0x20
    col = _rgb(int(rng.choice(TEAM if rng.random() < 0.7 else PALETTE)))
    col = np.clip(col + rng.normal(0, 0.02, 3), 0, 1)
    shadow = np.floor(col * 255 / 4) / 255
    if rng.random() < 0.05:
        shadow = col * rng.uniform(0.1, 0.4)
    a = g[..., 3:]
    for dx, c in ((k, shadow), (0, col)):
        if c is shadow and rng.random() < 0.03:
            continue
        ys, xs = y0 + dx, pad + dx
        reg = img[ys : ys + 8 * k, xs : xs + g.shape[1]]
        reg[:] = reg * (1 - a) + (c * g[..., :3]) * a
    if rng.random() < 0.25:  # another overlay on top (semi-transparent app)
        oc = rng.random(3).astype(np.float32) * rng.uniform(0, 0.4)
        al = rng.uniform(0.15, 0.6)
        img = img * (1 - al) + oc * al
    if rng.random() < 0.15:
        img = cv2.GaussianBlur(img, (0, 0), rng.uniform(0.3, 0.8) * k)
    img = np.clip(img + rng.normal(0, rng.uniform(0, 0.03), img.shape), 0, 1)
    img = (img * 255).astype(np.uint8)
    # crop like inference, with row / end jitter
    jy = int(rng.integers(-k // 2, k // 2 + 1)) if k > 1 else 0
    x0 = pad + int(rng.integers(-k, k + 1))
    x1 = pad + g.shape[1] + int(rng.integers(-k, k + 1))
    return norm_crop(img, y0 + jy, x0, x1, k), text


def fonts_weighted() -> tuple[list[BankFont], np.ndarray]:
    fs = list(bank())
    p = np.array([10.0 if f.fid == "vanilla" else 1.0 for f in fs])
    return fs, p / p.sum()
