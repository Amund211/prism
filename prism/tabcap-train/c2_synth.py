"""C2: synthetic data for CRNN v2. Two sample kinds:
- name: a name crop (as i4_synth.sample), sometimes with the team letter
  glued in front (target "L name"), as the real name regions can have.
- row: a whole tab row: [Lunar icon] [bold?] letter, space, name, gap,
  yellow score. Respawning rows (no letter), NPC rows, rank rows.
Targets use one space between words. Crop = i4_synth.norm_crop."""

import numpy as np

from i4_synth import CHARS, PALETTE, TEAM, _rgb, _scene, rand_name, render_rgba
from prism.overlay.tabcap.reader.front import norm_crop

TEAMS = ["red", "blue", "green", "yellow", "aqua", "white", "pink", "gray"]
LETTER = {
    "red": "R",
    "blue": "B",
    "green": "G",
    "yellow": "Y",
    "aqua": "A",
    "white": "W",
    "pink": "P",
    "gray": "S",
}
TEAM_RGB = dict(zip(TEAMS, TEAM))
# team tokens (B reader): one output symbol per team in place of the letter
TOKEN = dict(zip(TEAMS, "①②③④⑤⑥⑦⑧"))
TOKEN_TEAM = {v: k for k, v in TOKEN.items()}
CHARS_T = CHARS + "".join(TOKEN.values())
# row kind tokens (no letter, in the lobby): respawning = gray name,
# spectator = white name.
# Appended, so token models without them keep their ids.
KIND = {"respawning": "⑨", "spectator": "⑩"}
KIND_TOKEN = {v: k for k, v in KIND.items()}
CHARS_K = CHARS_T + "".join(KIND.values())
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
        img[
            y0 - k : y0 + 9 * k,
            pad - 2 * k : pad - 2 * k + int(rng.integers(1, 3)) * k // 1,
        ] = c
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


def head(rng, k):
    """player head: 8x8 random skin-like block, opaque"""
    base = rng.uniform(0.2, 0.9, 3).astype(np.float32)
    px = np.clip(base + rng.normal(0, 0.12, (8, 8, 3)), 0, 1).astype(np.float32)
    rgb = np.kron(px, np.ones((k, k, 1), np.float32))
    return np.ones(rgb.shape[:2], np.float32), rgb


def ping_bars(rng, k):
    """5 ping bars, 10 x 8 GUI px, green (or yellow / red)"""
    col = _rgb(int(rng.choice([0x55FF55, 0x55FF55, 0xFFFF55, 0xFF5555])))
    m = np.zeros((8, 10), np.float32)
    for i in range(5):
        if rng.random() < 0.9:
            m[8 - 2 * (i + 1) + 1 :, 2 * i] = 1
    m = np.kron(m, np.ones((k, k), np.float32))
    return m, m[..., None] * col


def hearts(rng, k):
    """health as hearts: 2-10 red hearts, 9 GUI px apart"""
    n = int(rng.integers(2, 11))
    h = np.array(
        [
            [0, 1, 1, 0, 1, 1, 0],
            [1, 1, 1, 1, 1, 1, 1],
            [1, 1, 1, 1, 1, 1, 1],
            [0, 1, 1, 1, 1, 1, 0],
            [0, 0, 1, 1, 1, 0, 0],
            [0, 0, 0, 1, 0, 0, 0],
        ],
        np.float32,
    )
    m = np.zeros((8, 9 * n), np.float32)
    for i in range(n):
        m[1:7, 9 * i : 9 * i + 7] = h
    m = np.kron(m, np.ones((k, k), np.float32))
    return m, m[..., None] * _rgb(0xFF5555)


OBF = [chr(c) for c in range(33, 256) if c not in range(127, 161)]
LINES = [
    "You are playing on MC.HYPIXEL.NET",
    "Ranks, Boosters & MORE! STORE.HYPIXEL.NET",
    "Kills: 0 Final Kills: 0 Beds Broken: 0",
    "Playing BED WARS on MC.HYPIXEL.NET",
    "Kills: 3 Final Kills: 1 Beds Broken: 2",
    "www.hypixel.net",
    "BED WARS",
]


def negative_sample(rng, f, kd="hard"):
    """rows the reader must drop (target ""): header / footer text, obfuscated
    (§k) names, heart-only rows"""
    k = int(rng.choice(K_DIST[kd]))
    u = rng.random()
    parts = []
    if u < 0.45:  # header / footer: 1-3 coloured words, maybe cut
        words = LINES[int(rng.integers(len(LINES)))].split(" ")
        a0 = int(rng.integers(0, max(1, len(words) - 1)))
        for w in words[a0 : a0 + int(rng.integers(2, 6))]:
            a, c = _trim(
                *piece(f, w, k, int(rng.choice(PALETTE[1:])), bold=rng.random() < 0.3)
            )
            parts.append((a, c, int(round(f.w[32] * k))))
    elif u < 0.85:  # obfuscated name, maybe head and ping bars
        if rng.random() < 0.6:
            parts.append((*head(rng, k), k))
        txt = "".join(rng.choice(OBF, int(rng.integers(3, 17))))
        a, c = _trim(*piece(f, txt, k, int(rng.choice([0xFFFFFF, 0xAAAAAA] + TEAM))))
        parts.append((a, c, int(rng.integers(2, 20)) * k))
        if rng.random() < 0.7:
            parts.append((*ping_bars(rng, k), 0))
    else:  # hearts only
        parts.append((*hearts(rng, k), 0))
    img, y0, x0, x1 = compose(rng, k, parts)
    return norm_crop(img, y0, x0 + _jit(rng, k), x1 + _jit(rng, k), k), ""


def row_sample_v3(rng, f, kd="hard", tokens=True, kinds=False):
    """row_sample plus: player head (lobby), ping bars, hearts as health,
    faint text behind the row. kinds: no-letter gray rows get the respawning
    token, white rows the spectator token"""
    k = int(rng.choice(K_DIST[kd]))
    sp = int(round(f.w[32] * k))
    u = rng.random()
    parts, words = [], []
    if rng.random() < 0.15:
        parts.append((*icon(rng, k), k))
    elif rng.random() < 0.15:
        parts.append((*head(rng, k), k))
    if u < 0.75:
        team = TEAMS[int(rng.integers(8))]
        col = TEAM_RGB[team]
        a, c = _trim(*piece(f, LETTER[team], k, col, bold=rng.random() < 0.5))
        parts.append((a, c, sp + int(rng.integers(0, 2)) * k))
        words.append(TOKEN[team] if tokens else LETTER[team])
        name = rand_name(rng)
    elif u < 0.88:
        col = int(rng.choice([0xFFFFFF, 0xAAAAAA, 0x555555] + TEAM))
        if kinds and rng.random() < 0.5:
            col = int(rng.choice([0xFFFFFF, 0xAAAAAA]))
        if kinds and col == 0xAAAAAA:
            words.append(KIND["respawning"])
        elif kinds and col == 0xFFFFFF:
            words.append(KIND["spectator"])
        name = rand_name(rng)
    elif u < 0.93:
        col = 0xFFFFFF
        name = "".join(
            rng.choice(
                list("abcdefghijklmnopqrstuvwxyz0123456789"), int(rng.integers(8, 11))
            )
        )
    else:
        col = int(rng.choice(PALETTE[1:]))
        rank = "".join(
            rng.choice(list("ABCDEFGHIJKLMNOPQRSTUVWXYZ+"), int(rng.integers(1, 5)))
        )
        name = f"[{rank}] {rand_name(rng)}"
    a, c = _trim(*piece(f, name, k, col))
    words.append(name)
    tail = rng.random()
    if u < 0.93 and tail < 0.6:  # health number, gap 1-40 GUI px
        parts.append((a, c, int(rng.integers(1, 40)) * k))
        s = (
            "20"
            if rng.random() < 0.5
            else ("0" if u >= 0.88 else str(int(rng.integers(1, 21))))
        )
        a, c = _trim(*piece(f, s, k, YELLOW))
        words.append(s)
    elif u < 0.93 and tail < 0.72:  # hearts (no target)
        parts.append((a, c, int(rng.integers(2, 20)) * k))
        a, c = hearts(rng, k)
    if rng.random() < 0.25:  # ping bars at the row end (no target)
        parts.append((a, c, int(rng.integers(2, 30)) * k))
        a, c = ping_bars(rng, k)
    parts.append((a, c, 0))
    img, y0, x0, x1 = compose(rng, k, parts)
    if rng.random() < 0.1:  # faint text behind (chat / scoreboard through the tab)
        ghost, _, _, _ = compose(
            rng,
            k,
            [
                (
                    *_trim(
                        *piece(
                            f,
                            rand_name(rng) + " " + rand_name(rng),
                            k,
                            int(rng.choice(PALETTE[1:])),
                        )
                    ),
                    0,
                )
            ],
        )
        gw = min(ghost.shape[1], img.shape[1])
        al = rng.uniform(0.15, 0.4)
        img[:, :gw] = (img[:, :gw] * (1 - al) + ghost[:, :gw] * al).astype(np.uint8)
    jy = int(rng.integers(-k // 2, k // 2 + 1)) if k > 1 else 0
    return norm_crop(img, y0 + jy, x0 + _jit(rng, k), x1 + _jit(rng, k), k), " ".join(
        words
    )


def row_sample(rng, f, kd="hard", tokens=False):
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
        words.append(TOKEN[team] if tokens else LETTER[team])
        name = rand_name(rng)
    elif u < 0.88:  # respawning / spectator: no letter
        col = int(rng.choice([0xFFFFFF, 0xAAAAAA, 0x555555] + TEAM))
        name = rand_name(rng)
    elif u < 0.93:  # npc
        col = 0xFFFFFF
        name = "".join(
            rng.choice(
                list("abcdefghijklmnopqrstuvwxyz0123456789"), int(rng.integers(8, 11))
            )
        )
    else:  # lobby / rank row
        col = int(rng.choice(PALETTE[1:]))
        rank = "".join(
            rng.choice(list("ABCDEFGHIJKLMNOPQRSTUVWXYZ+"), int(rng.integers(1, 5)))
        )
        name = f"[{rank}] {rand_name(rng)}"
    a, c = _trim(*piece(f, name, k, col))
    words.append(name)
    has_score = u < 0.93 and rng.random() < 0.85
    parts.append((a, c, int(rng.integers(2, 40)) * k if has_score else 0))
    if has_score:
        s = (
            "20"
            if rng.random() < 0.5
            else ("0" if u >= 0.88 else str(int(rng.integers(1, 21))))
        )
        a, c = _trim(*piece(f, s, k, YELLOW))
        parts.append((a, c, 0))
        words.append(s)
    img, y0, x0, x1 = compose(rng, k, parts)
    jy = int(rng.integers(-k // 2, k // 2 + 1)) if k > 1 else 0
    return norm_crop(img, y0 + jy, x0 + _jit(rng, k), x1 + _jit(rng, k), k), " ".join(
        words
    )


def name_sample(rng, f, kd="hard", tokens=False):
    k = int(rng.choice(K_DIST[kd]))
    col = int(rng.choice(TEAM if rng.random() < 0.7 else PALETTE))
    name = rand_name(rng)
    if rng.random() < 0.08:
        name = (
            "["
            + "".join(
                rng.choice(list("ABCDEFGHIJKLMNOPQRSTUVWXYZ+"), int(rng.integers(1, 5)))
            )
            + "] "
            + name
        )
    parts, words = [], []
    if rng.random() < 0.05:  # team letter glued to the name region
        team = TEAMS[int(rng.integers(8))]
        if tokens:  # a token must match its colour
            col = TEAM_RGB[team]
        L = LETTER[team]
        a, c = _trim(*piece(f, L, k, col))
        parts.append((a, c, int(round(f.w[32] * k))))
        words.append(TOKEN[team] if tokens else L)
    a, c = _trim(*piece(f, name, k, col))
    parts.append((a, c, 0))
    words.append(name)
    img, y0, x0, x1 = compose(rng, k, parts)
    jy = int(rng.integers(-k // 2, k // 2 + 1)) if k > 1 else 0
    return norm_crop(img, y0 + jy, x0 + _jit(rng, k), x1 + _jit(rng, k), k), " ".join(
        words
    )


assert all(c in CHARS for c in "RBGYAWPS0123456789 []+")
