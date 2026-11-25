"""Random tab lists and styles for training data. All sprites are made here
(no Lunar, Mojang or player art), so the reader learns the layout, not
the exact icons."""

from dataclasses import dataclass

import numpy as np

from synth.canvas import Sprite
from synth.tablist import LUNAR, VANILLA, Style, TabRow, TabSpec

TEAMS = {  # Hypixel team -> (letter, color code)
    "red": ("R", "c"),
    "blue": ("B", "9"),
    "green": ("G", "a"),
    "yellow": ("Y", "e"),
    "aqua": ("A", "b"),
    "white": ("W", "f"),
    "pink": ("P", "d"),
    "gray": ("S", "7"),
}
NAME_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
PINGS = (0, 40, 160, 350, 700, 1200, -1)
HEADERS = (
    ("§bYou are playing on §e§lMC.HYPIXEL.NET",),
    ("", "§bYou are playing on §e§lMC.HYPIXEL.NET", ""),
)


@dataclass(frozen=True)
class Options:
    min_rows: int = 2
    max_rows: int = 16
    p_icon: float = 0.4  # Lunar icon before the name
    p_badge: float = 0.1  # badge after the name
    # Hypixel respawning / eliminated players: gray (or white) name, no team
    # letter, score shown; seen on Forge and Lunar. Not gamemode spectator.
    p_no_team: float = 0.12
    p_white_no_team: float = 0.25
    p_spectator: float = 0.02  # gamemode spectator: italic, no score
    p_score: float = 0.8
    p_header: float = 0.9
    teams: int = 4


def random_name(rng: np.random.Generator) -> str:
    n = int(rng.integers(3, 17))
    return "".join(NAME_CHARS[i] for i in rng.integers(0, len(NAME_CHARS), n))


def random_head(rng: np.random.Generator) -> Sprite:
    """An 8 x 8 face: skin, hair band, eyes"""
    skin = rng.integers(40, 256, 3)
    hair = rng.integers(0, 256, 3)
    tex = np.empty((8, 8, 4), np.uint8)
    tex[..., :3] = np.clip(skin + rng.integers(-12, 13, (8, 8, 3)), 0, 255)
    tex[..., 3] = 255
    tex[: int(rng.integers(1, 4)), :, :3] = hair
    tex[4, 1:3, :3] = tex[4, 5:7, :3] = rng.integers(0, 256, 3)
    return Sprite(tex, 8, 8)


def _disc(size: int, r0: float, r1: float) -> np.ndarray:
    """Alpha of a ring with radii r0..r1 (of the half size), anti-aliased"""
    c = (np.arange(size) + 0.5) / size * 2 - 1
    d = np.hypot(c[None, :], c[:, None])
    return np.clip(np.minimum(d - r0, r1 - d) * size / 2 + 0.5, 0, 1)


def random_icon(rng: np.random.Generator, res: int) -> Sprite:
    """A round crescent-like icon, res texels per GUI px"""
    size = 8 * res
    a = _disc(size, 0.0, 0.95)
    off = rng.uniform(0.2, 0.6)
    c = (np.arange(size) + 0.5) / size * 2 - 1
    cut = np.hypot(c[None, :] - off, c[:, None] + off / 2) < rng.uniform(0.5, 0.8)
    a[cut] = 0
    tex = np.zeros((size, size, 4), np.uint8)
    tex[..., :3] = rng.integers(150, 256, 3)
    tex[..., 3] = (a * 255).astype(np.uint8)
    return Sprite(tex, 8, 8)


def random_badge(rng: np.random.Generator, res: int) -> Sprite:
    """A round badge with a colored ring and a dark center"""
    size = 8 * res
    tex = np.zeros((size, size, 4), np.uint8)
    ring = _disc(size, rng.uniform(0.6, 0.8), 0.98)
    inner = _disc(size, 0.0, 0.7)
    tex[..., :3] = (
        rng.integers(0, 256, 3) * ring[..., None]
        + rng.integers(0, 120, 3) * (1 - ring[..., None])
    ).astype(np.uint8)
    tex[..., 3] = (np.maximum(ring, inner) * 255).astype(np.uint8)
    return Sprite(tex, 8, 8)


def random_spec(rng: np.random.Generator, opts: Options) -> TabSpec:
    n = int(rng.integers(opts.min_rows, opts.max_rows + 1))
    teams = list(TEAMS)[: opts.teams]
    picked = sorted(rng.integers(0, len(teams), n).tolist())
    res = int(rng.choice([1, 2, 4]))
    rows = []
    for t in picked:
        letter, c = TEAMS[teams[t]]
        spectator = bool(rng.random() < opts.p_spectator)
        name = random_name(rng)
        if spectator:
            text = name
        elif rng.random() < opts.p_no_team:
            text = f"§{'f' if rng.random() < opts.p_white_no_team else '7'}{name}"
        else:
            text = f"§{c}§l{letter} §{c}{name}"
        rows.append(
            TabRow(
                text=text,
                score=int(rng.integers(0, 21)),
                ping_ms=int(rng.choice(PINGS)),
                head=random_head(rng),
                icon=random_icon(rng, res) if rng.random() < opts.p_icon else None,
                badge=random_badge(rng, res) if rng.random() < opts.p_badge else None,
                spectator=spectator,
            )
        )
    header: tuple[str, ...] = ()
    footer: tuple[str, ...] = ()
    if rng.random() < opts.p_header:
        header = HEADERS[int(rng.integers(0, len(HEADERS)))]
        k, f, b = rng.integers(0, 15, 3)
        footer = (
            f"§bKills: §e{k} §bFinal Kills: §e{f} §bBeds Broken: §e{b}",
            "§aRanks, Boosters & MORE! §c§lSTORE.HYPIXEL.NET",
        )
    return TabSpec(
        rows=tuple(rows),
        header=header,
        footer=footer,
        score=bool(rng.random() < opts.p_score),
    )


def random_style(rng: np.random.Generator) -> Style:
    base = LUNAR if rng.random() < 0.5 else VANILLA
    return Style(
        heads=bool(rng.random() < 0.9),
        ping=bool(rng.random() < 0.9),
        box_alpha=int(rng.integers(96, 160)),
        slot_color=base.slot_color,
        slot_alpha=base.slot_alpha,
        slot_over_box=base.slot_over_box,
        bold_width_bug=base.bold_width_bug,
        badge_width=base.badge_width,
    )
