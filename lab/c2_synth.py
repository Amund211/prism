"""C2: synthetic data for CRNN v2. Two sample kinds:
- name: a name crop (as i4_synth.sample), sometimes with the team letter
  glued in front (target "L name"), as the real name regions can have.
- row: a whole tab row: [Lunar icon] [bold?] letter, space, name, gap,
  yellow score. Respawning rows (no letter), NPC rows, rank rows.
Targets use one space between words. Crop = i4_synth.norm_crop."""

import numpy as np

from i4_synth import CHARS, PALETTE, TEAM, _rgb, _scene, norm_crop, rand_name, render_rgba
from rowparse import LETTER

TEAMS = ["red", "blue", "green", "yellow", "aqua", "white", "pink", "gray"]
TEAM_RGB = dict(zip(TEAMS, TEAM))
YELLOW = 0xFFFF55
K_DIST = {"base": [1, 2, 2, 3, 3, 4], "hard": [1, 1, 1, 2, 2, 3, 4]}


def piece(f, text, k, color, bold=False):
    """(alpha 8k x W, rgb 8k x W x 3) of text in color (texture x color)"""
    g = render_rgba(f, text, k)
    if bold:  # Minecraft bold: the glyphs again at +1 GUI px
        b = np.zeros((g.shape[0], g.shape[1] + k, 4), np.float32)
        b[:, : g.shape[1]] = g
        b[:, k:] = np.where(g[..., 3:] > b[:, k:, 3:], g, b[:, k:])
        g = b
    return g[..., 3], g[..., :3] * _rgb(color)


def icon(rng, k):
    """Lunar-like moon icon, 8k x 8k, white-gray"""
    n = 8
    yy, xx = np.mgrid[0:n, 0:n] + 0.5
    disk = (yy - 4) ** 2 + (xx - 4) ** 2 <= 12
    cut = (yy - 3) ** 2 + (xx - 5.5) ** 2 <= 6
    m = (disk & ~cut).astype(np.float32)
    if rng.random() < 0.5:
        m = (rng.random((n, n)) < 0.5).astype(np.float32) * disk
    m = np.kron(m, np.ones((k, k), np.float32))
    return m, m[..., None] * np.float32(rng.uniform(0.6, 1.0))


def compose(rng, k, parts):
    """parts: [(alpha, rgb, gap_after_px)] -> uint8 canvas, glyph y0, x0, x1"""
    W = sum(a.shape[1] + g for a, _, g in parts)
    pad = 6 * k
    Hc, Wc = 12 * k, W + 2 * pad
    y0 = 2 * k
    img = _scene(rng, Hc, Wc) * 0.5
    if rng.random() < 0.85:
        img = img * (1 - 0.125) + 0.125
    if rng.random() < 0.3:  # head edge at the left of the crop
        c = rng.random(3).astype(np.float32)
        img[y0 - k : y0 + 9 * k, pad - 2 * k : pad - 2 * k + int(rng.integers(1, 3)) * k // 1] = c
    x = pad
    no_shadow = rng.random() < 0.03
    for a, rgb, g in parts:
        a3 = a[..., None]
        for d, col in ((k, np.floor(rgb * 255 / 4) / 255), (0, rgb)):
            if d and no_shadow:
                continue
            reg = img[y0 + d : y0 + d + a.shape[0], x + d : x + d + a.shape[1]]
            reg[:] = reg * (1 - a3) + col * a3
        x += a.shape[1] + g
    if rng.random() < 0.25:
        oc = rng.random(3).astype(np.float32) * rng.uniform(0, 0.4)
        al = rng.uniform(0.15, 0.6)
        img = img * (1 - al) + oc * al
    if rng.random() < 0.15:
        import cv2

        img = cv2.GaussianBlur(img, (0, 0), rng.uniform(0.3, 0.8) * k)
    img = np.clip(img + rng.normal(0, rng.uniform(0, 0.03), img.shape), 0, 1)
    return (img * 255).astype(np.uint8), y0, pad, pad + W


def _trim(a, rgb):
    cols = np.flatnonzero(a.max(0) > 0)
    if len(cols) == 0:
        return a, rgb
    return a[:, cols[0] : cols[-1] + 1], rgb[:, cols[0] : cols[-1] + 1]


def _jit(rng, k):
    return int(rng.integers(-k, k + 1))


def row_sample(rng, f, kd="hard"):
    k = int(rng.choice(K_DIST[kd]))
    sp = int(round(f.w[32] * k))
    u = rng.random()
    parts, words = [], []
    if rng.random() < 0.15:
        a, c = icon(rng, k)
        parts.append((a, c, k))
    if u < 0.75:  # team row
        team = TEAMS[int(rng.integers(8))]
        col = TEAM_RGB[team]
        a, c = _trim(*piece(f, LETTER[team], k, col, bold=rng.random() < 0.5))
        parts.append((a, c, sp + int(rng.integers(0, 2)) * k))
        words.append(LETTER[team])
        name = rand_name(rng)
    elif u < 0.88:  # respawning / spectator: no letter
        col = int(rng.choice([0xFFFFFF, 0xAAAAAA, 0x555555] + TEAM))
        name = rand_name(rng)
    elif u < 0.93:  # npc
        col = 0xFFFFFF
        name = "".join(rng.choice(list("abcdefghijklmnopqrstuvwxyz0123456789"), int(rng.integers(8, 11))))
    else:  # lobby / rank row
        col = int(rng.choice(PALETTE[1:]))
        rank = "".join(rng.choice(list("ABCDEFGHIJKLMNOPQRSTUVWXYZ+"), int(rng.integers(1, 5))))
        name = f"[{rank}] {rand_name(rng)}"
    a, c = _trim(*piece(f, name, k, col))
    words.append(name)
    has_score = u < 0.93 and rng.random() < 0.85
    parts.append((a, c, int(rng.integers(2, 40)) * k if has_score else 0))
    if has_score:
        s = "20" if rng.random() < 0.5 else ("0" if u >= 0.88 else str(int(rng.integers(1, 21))))
        a, c = _trim(*piece(f, s, k, YELLOW))
        parts.append((a, c, 0))
        words.append(s)
    img, y0, x0, x1 = compose(rng, k, parts)
    jy = int(rng.integers(-k // 2, k // 2 + 1)) if k > 1 else 0
    return norm_crop(img, y0 + jy, x0 + _jit(rng, k), x1 + _jit(rng, k), k), " ".join(words)


def name_sample(rng, f, kd="hard"):
    k = int(rng.choice(K_DIST[kd]))
    col = int(rng.choice(TEAM if rng.random() < 0.7 else PALETTE))
    name = rand_name(rng)
    if rng.random() < 0.08:
        name = "[" + "".join(rng.choice(list("ABCDEFGHIJKLMNOPQRSTUVWXYZ+"), int(rng.integers(1, 5)))) + "] " + name
    parts, words = [], []
    if rng.random() < 0.05:  # team letter glued to the name region
        L = LETTER[TEAMS[int(rng.integers(8))]]
        a, c = _trim(*piece(f, L, k, col))
        parts.append((a, c, int(round(f.w[32] * k))))
        words.append(L)
    a, c = _trim(*piece(f, name, k, col))
    parts.append((a, c, 0))
    words.append(name)
    img, y0, x0, x1 = compose(rng, k, parts)
    jy = int(rng.integers(-k // 2, k // 2 + 1)) if k > 1 else 0
    return norm_crop(img, y0 + jy, x0 + _jit(rng, k), x1 + _jit(rng, k), k), " ".join(words)


assert all(c in CHARS for c in "RBGYAWPS0123456789 []+")
