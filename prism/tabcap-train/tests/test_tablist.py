from typing import Any

import numpy as np
import pytest

from synth.canvas import Sprite
from synth.tablist import (
    LUNAR,
    VANILLA,
    Style,
    TabRow,
    TabSpec,
    layout,
    ping_bucket,
    render,
)
from tests.helpers import block_font

FONT = block_font()  # every char 6 wide, space 4
GUI_W = 960


def row(text: str = "§9§lB §9ab", **kw: Any) -> TabRow:
    kw.setdefault("score", 20)
    kw.setdefault("ping_ms", 50)
    return TabRow(text=text, **kw)


def test_single_column() -> None:
    spec = TabSpec(rows=(row(), row("§c§lR §ccd", score=7, ping_ms=200)))
    lay = layout(spec, FONT, GUI_W, VANILLA)
    # name width with the 1.8.9 bold bug: B 7, space 5, a 7, b 7
    assert lay.name_width == 26
    assert lay.score_width == 16  # " 20"
    assert lay.slot_width == 9 + 26 + 16 + 13
    assert lay.box == (447, 9, 513, 28)
    r0, r1 = lay.rows
    assert r0.slot == (448, 10, 512, 18)
    assert r1.slot == (448, 19, 512, 27)
    assert r0.head == (448, 10)
    assert r0.text == (457, 10)
    assert r0.score == (488, 10, "§e20")
    assert r1.score == (494, 19, "§e7")
    assert r0.ping == (501, 10, 0)
    assert r1.ping == (501, 19, 1)
    assert r0.icon is None and r0.badge is None


def test_header_footer() -> None:
    spec = TabSpec(rows=(row(), row()), header=("hello",), footer=("x" * 20,))
    lay = layout(spec, FONT, GUI_W, VANILLA)
    assert lay.box == (419, 9, 541, 48)
    assert lay.header == ((465, 10, "hello"),)
    assert lay.footer == ((420, 39, "x" * 20),)
    assert lay.rows[0].slot == (448, 20, 512, 28)
    black = [r for r in lay.rects if r[4] == 0x000000 and r[5] == 128]
    assert [r[:4] for r in black] == [
        (419, 9, 541, 19),
        (419, 19, 541, 38),
        (419, 38, 541, 48),
    ]


def test_columns() -> None:
    spec = TabSpec(rows=tuple(row() for _ in range(25)))
    lay = layout(spec, FONT, GUI_W, VANILLA)
    assert len(lay.rows) == 25
    assert lay.rows[12].slot[:2] == (414, 10 + 12 * 9)
    assert lay.rows[13].slot[:2] == (414 + 64 + 5, 10)
    # width / 2 +- l1 / 2 + 1 with integer division: 133 // 2 = 66
    assert lay.box == (480 - 66 - 1, 9, 480 + 66 + 1, 10 + 13 * 9)


def test_max_80_rows() -> None:
    spec = TabSpec(rows=tuple(row() for _ in range(90)))
    assert len(layout(spec, FONT, GUI_W, VANILLA).rows) == 80


def test_width_cap() -> None:
    spec = TabSpec(rows=(row("a" * 200),))
    lay = layout(spec, FONT, GUI_W, VANILLA)
    assert lay.slot_width == GUI_W - 50


def test_no_heads_no_score() -> None:
    style = Style(heads=False)
    spec = TabSpec(rows=(row(),), score=False)
    lay = layout(spec, FONT, GUI_W, style)
    assert lay.slot_width == 26 + 13
    r = lay.rows[0]
    assert r.head is None
    assert r.text == (r.slot[0], 10)
    assert r.score is None
    assert r.ping == (r.slot[0] + lay.slot_width - 11, 10, 0)


def test_score_needs_room() -> None:
    # l5 - k5 must be > 5: a 1-digit score is " 7" = 10 wide, so it is drawn;
    # with an empty score column nothing is
    spec = TabSpec(rows=(row(score=None),))
    lay = layout(spec, FONT, GUI_W, VANILLA)
    assert lay.score_width == 0
    assert lay.rows[0].score is None


def test_spectator() -> None:
    spec = TabSpec(rows=(row("ab", spectator=True),))
    lay = layout(spec, FONT, GUI_W, VANILLA)
    r = lay.rows[0]
    assert r.text_prefix == "§o"
    assert r.text_color == 0x90FFFFFF
    assert r.score is None


def test_lunar_icon_and_badge() -> None:
    icon = Sprite(np.full((8, 8, 4), 255, np.uint8), 8, 8)
    style = Style(badge_gap=2)
    spec = TabSpec(
        rows=(row(icon=icon, badge=icon), row("§9§lB §9abcdef")),
    )
    lay = layout(spec, FONT, GUI_W, style)
    # row 0: 26 + icon 9 + gap 2 + badge 8 = 45; row 1: 7 + 5 + 6 * 7 = 54
    assert lay.name_width == 54
    r0 = lay.rows[0]
    x = r0.slot[0]
    assert r0.icon == (x + 9, r0.slot[1])
    assert r0.text == (x + 18, r0.slot[1])
    assert r0.badge == (x + 18 + 26 + 2, r0.slot[1])
    # score is placed from the text start without the icon
    assert r0.score is not None
    assert r0.score[0] == x + 9 + 54 + 1 + 16 - 12

    style = Style(icon_width=0, badge_width=0)
    lay = layout(TabSpec(rows=(row(icon=icon, badge=icon),)), FONT, GUI_W, style)
    assert lay.name_width == 26
    style = Style(icon_width=8, badge_width=9)
    lay = layout(TabSpec(rows=(row(icon=icon, badge=icon),)), FONT, GUI_W, style)
    assert lay.name_width == 26 + 8 + 9


@pytest.mark.parametrize(
    "ms, bucket",
    [
        (-1, 5),
        (0, 0),
        (149, 0),
        (150, 1),
        (299, 1),
        (300, 2),
        (600, 3),
        (999, 3),
        (1000, 4),
    ],
)
def test_ping_bucket(ms: int, bucket: int) -> None:
    assert ping_bucket(ms) == bucket


def fake_icons() -> Sprite:
    tex = np.zeros((256, 256, 4), np.uint8)
    tex[176:184, 0:10] = (0, 255, 0, 255)  # bucket 0
    return Sprite(tex, 256, 256)


def test_render() -> None:
    bg = np.full((1080, 1920, 3), 200, np.uint8)
    head = Sprite(np.full((8, 8, 4), (255, 0, 0, 255), np.uint8), 8, 8)
    icon = Sprite(np.full((16, 16, 4), (0, 0, 7, 255), np.uint8), 8, 8)
    badge = Sprite(np.full((8, 8, 4), (9, 0, 0, 255), np.uint8), 8, 8)
    spec = TabSpec(
        rows=(row(head=head), row(icon=icon, badge=badge)),
        header=("hi",),
        footer=("f",),
    )
    out = render(bg, spec, FONT, 2, LUNAR, icons=fake_icons())
    r1 = out.layout.rows[1]
    ix, iy = r1.icon  # type: ignore[misc]
    assert tuple(out.image[2 * iy + 1, 2 * ix + 15]) == (0, 0, 7)
    bx, by = r1.badge  # type: ignore[misc]
    assert tuple(out.image[2 * by, 2 * bx]) == (9, 0, 0)
    fx, fy, _ = out.layout.footer[0]
    assert tuple(out.image[2 * fy, 2 * fx]) == (255, 255, 255)
    x0, y0, x1, y1 = out.box
    assert out.box == tuple(2 * v for v in out.layout.box)
    assert (out.image[:y0] == 200).all() and (out.image[:, :x0] == 200).all()
    assert (out.image[y1:] == 200).all() and (out.image[:, x1:] == 200).all()
    # header box: black 128
    assert tuple(out.image[y0, x0]) == (100, 100, 100)
    r = out.layout.rows[0]
    hx, hy = r.head  # type: ignore[misc]
    assert tuple(out.image[2 * hy, 2 * hx]) == (255, 0, 0)
    tx, ty = r.text
    assert tuple(out.image[2 * ty, 2 * tx + 2]) == (0x55, 0x55, 0xFF)  # B
    px, py, _ = r.ping  # type: ignore[misc]
    assert tuple(out.image[2 * py, 2 * px]) == (0, 255, 0)
    # empty slot area (Lunar): black 144 over the world, not over the box
    sx = 2 * (r.slot[2] - 12)
    v = int(np.floor(200 * 111 / 255 + 0.5))
    assert tuple(out.image[2 * r.slot[1], sx]) == (v, v, v)


def test_render_vanilla_slot_and_no_icons() -> None:
    bg = np.full((540, 960, 3), 200, np.uint8)
    out = render(bg, TabSpec(rows=(row(),)), FONT, 1, VANILLA)
    r = out.layout.rows[0]
    v = int(np.floor((200 * 127 / 255) * 223 / 255 + 255 * 32 / 255 + 0.5))
    assert tuple(out.image[r.slot[1], r.slot[2] - 1]) == (v, v, v)


def test_render_spectator() -> None:
    bg = np.zeros((540, 960, 3), np.uint8)
    out = render(bg, TabSpec(rows=(row("a", spectator=True),)), FONT, 1, VANILLA)
    r = out.layout.rows[0]
    # 0x90 alpha: 255 * 144 / 255 over the slot (dark), italic top row at +1
    px = out.image[r.text[1], r.text[0] + 1]
    assert px[0] > 140
