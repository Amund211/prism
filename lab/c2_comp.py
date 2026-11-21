"""Composite rows: the tabcap synth generator (tabcap-synth-calib worktree) draws a
whole tab list on a real plain shot; our front step finds the rows; crops are cut
as at inference (regions_of + norm_crop). Target per front row: token name
[score] from the layout; a front row on a header / footer line -> "" (negative).
Backgrounds: plain shots of TRAIN games only (games 2 and 5 of 2026-11-21 are
test games: BG_GAME_STARTS)."""

import json
import sys
from functools import cache
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, "/home/amund/git/overlay/tabcap-synth-calib/prism/src")

from prism.overlay.tabcap.synth.canvas import Sprite  # noqa: E402
from prism.overlay.tabcap.synth.tablist import TabRow, TabSpec, render  # noqa: E402
from prism.overlay.tabcap.synth.text import BitmapFont  # noqa: E402
from prism.overlay.tabcap.synth.variety import random_badge, random_head, random_icon, random_style  # noqa: E402

from c2_synth import K_DIST, TEAMS, TOKEN  # noqa: E402
from g_bank import RP, BankFont  # noqa: E402
from i4_synth import norm_crop, rand_name  # noqa: E402
from rowparse import LETTER  # noqa: E402
from tl_front import front  # noqa: E402
from g_match import regions_of  # noqa: E402

CALIB = Path.home() / "git/overlay/test-fixtures/tabcap_synth_calib_2026-11-21"
# game start (s of day, = capture time - since_game_start_s) of the train games 1, 3, 4
BG_GAME_STARTS = {57961, 58306, 58898}
CODE = {"red": "c", "blue": "9", "green": "a", "yellow": "e", "aqua": "b", "white": "f", "pink": "d", "gray": "7"}
PINGS = (0, 40, 160, 350, 700, 1200, -1)
HEADERS = (("§bYou are playing on §e§lMC.HYPIXEL.NET",), ("", "§bYou are playing on §e§lMC.HYPIXEL.NET", ""))


def _t(stem: str) -> float:
    s = stem.split("-")[0]
    return int(s[:2]) * 3600 + int(s[2:4]) * 60 + float(s[4:])


@cache
def backgrounds() -> list[np.ndarray]:
    out = []
    for j in sorted(CALIB.glob("**/*-plain.json")):
        st = json.loads(j.read_text()).get("state", {}).get("since_game_start_s")
        if st is None or round(_t(j.stem) - st) not in BG_GAME_STARTS:
            continue
        out.append(np.asarray(Image.open(j.with_name(j.stem + "-0000ms.png")).convert("RGB")))
    return out


@cache
def _icons() -> Sprite:
    p = RP / "vanilla/1.8.9/assets/minecraft/textures/gui/icons.png"
    return Sprite(np.asarray(Image.open(p).convert("RGBA")), 256, 256)


_FONTS: dict[str, BitmapFont] = {}


def _font(f: BankFont) -> BitmapFont:
    if f.key not in _FONTS:
        _FONTS[f.key] = _load_font(f)
    return _FONTS[f.key]


def _load_font(f: BankFont) -> BitmapFont:
    p =RP / "vanilla/1.8.9/assets/minecraft/textures/font/ascii.png" if f.fid == "vanilla" else RP / "fonts" / f.fid / "ascii.png"
    tex = np.asarray(Image.open(p).convert("RGBA"))
    return BitmapFont(tex, hd=f.mode == "optifine", widths=dict(enumerate(f.w)))


def _spec(rng: np.random.Generator) -> tuple[TabSpec, list[str]]:
    n_teams = int(rng.choice([2, 4, 4, 8, 8]))
    teams = list(rng.permutation(TEAMS)[:n_teams])
    n = int(rng.integers(2, min(16, 2 * n_teams * 2) + 1))
    picked = sorted(rng.integers(0, n_teams, n).tolist())
    order = [t for t in TEAMS if t in teams]
    picked = sorted((teams[i] for i in picked), key=order.index)
    res = int(rng.choice([1, 2, 4]))
    score = bool(rng.random() < 0.8)
    rows, targets = [], []
    for team in picked:
        name = rand_name(rng)
        spectator = bool(rng.random() < 0.05)
        c = CODE[team]
        s = 20 if rng.random() < 0.5 else int(rng.integers(0, 21))
        if spectator:
            text = name
        elif rng.random() < 0.9:
            text = f"§{c}§l{LETTER[team]} §{c}{name}"
        else:
            text = f"§{c}§l{LETTER[team]}§{c} {name}"
        rows.append(TabRow(text=text, score=s, ping_ms=int(rng.choice(PINGS)), head=random_head(rng),
                           icon=random_icon(rng, res) if rng.random() < 0.4 else None,
                           badge=random_badge(rng, res) if rng.random() < 0.1 else None, spectator=spectator))
        words = [] if spectator else [TOKEN[team]]
        words.append(name)
        if score and not spectator:
            words.append(str(s))
        targets.append(" ".join(words))
    header: tuple[str, ...] = ()
    footer: tuple[str, ...] = ()
    if rng.random() < 0.9:
        header = HEADERS[int(rng.integers(len(HEADERS)))]
        k, f, b = rng.integers(0, 15, 3)
        footer = (f"§bKills: §e{k} §bFinal Kills: §e{f} §bBeds Broken: §e{b}",
                  "§aRanks, Boosters & MORE! §c§lSTORE.HYPIXEL.NET")
    return TabSpec(rows=tuple(rows), header=header, footer=footer, score=score), targets


def comp_rows(rng: np.random.Generator, f: BankFont, kd: str = "hard") -> list[tuple[np.ndarray, str]]:
    """One composite tab -> [(crop, target)] for the rows our front step finds"""
    bgs = backgrounds()
    bg = bgs[int(rng.integers(len(bgs)))]
    if rng.random() < 0.5:
        bg = bg[:, ::-1]
    bg = np.ascontiguousarray(np.roll(bg, int(rng.integers(bg.shape[1])), axis=1))
    k = int(rng.choice(K_DIST[kd]))
    spec, targets = _spec(rng)
    res = render(bg, spec, _font(f), k, random_style(rng), _icons())
    lay = res.layout
    rows_y = {rl.text[1] * k: t for rl, t in zip(lay.rows, targets)}
    neg_y = {y * k for _, y, _ in (*lay.header, *lay.footer)}
    rgb = res.image
    try:
        _, tab, prows = front(rgb)
    except Exception:
        return []
    if tab is None or not prows:
        return []
    out = []
    for g in regions_of(rgb, prows, tab.k):
        r = g.prow.row
        hit = [t for y, t in rows_y.items() if abs(r.y - y) <= k]
        if hit:
            t = hit[0]
        elif any(abs(r.y - y) <= k for y in neg_y):
            t = ""
        else:
            continue
        out.append((norm_crop(rgb, r.y, r.x0, r.x1, tab.k), t))
    return out
