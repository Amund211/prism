import numpy as np
import pytest

from prism.overlay.tabcap.synth.canvas import Canvas
from prism.overlay.tabcap.synth.text import (
    COLOR_CODES,
    BitmapFont,
    draw_string,
    parse_width_properties,
    shadow_color,
)
from tests.prism.overlay.tabcap.synth.helpers import block_font


def test_color_codes() -> None:
    assert len(COLOR_CODES) == 32
    assert COLOR_CODES[0] == 0x000000
    assert COLOR_CODES[6] == 0xFFAA00  # gold: the one special case
    assert COLOR_CODES[9] == 0x5555FF
    assert COLOR_CODES[15] == 0xFFFFFF
    assert COLOR_CODES[16 + 9] == 0x15153F
    assert COLOR_CODES[16 + 15] == 0x3F3F3F


def test_shadow_color() -> None:
    assert shadow_color(0xFFFFFF) == 0x3F3F3F
    assert shadow_color(0xFFFF55) == 0x3F3F15


@pytest.mark.parametrize(
    "cell, ink, width",
    [
        (8, 5, 6),  # last ink column + 1 + 1
        (8, 1, 2),
        (16, 10, 6),  # int(0.5 + 10 * 8 / 16) + 1
        (16, 9, 6),  # 4.5 + 0.5 -> 5, + 1
        (32, 5, 2),  # int(0.5 + 1.25) + 1
    ],
)
def test_char_width_from_texture(cell: int, ink: int, width: int) -> None:
    font = block_font(cell, {"a": ink})
    assert font.char_width("a") == width


def test_char_width_special() -> None:
    font = block_font()
    assert font.char_width(" ") == 4
    assert font.char_width("§") == -1
    assert font.char_width("é") == 0  # not in the ascii page


def test_hd_widths() -> None:
    # OptiFine HD rules (cell > 8): float widths, wider space, bold + 0.5
    font = block_font(16, {"a": 9, "b": 10}, hd=True)
    assert font.char_width("a") == 9 * 8 / 16 + 1
    assert font.char_width("b") == 6.0
    assert font.char_width(" ") == (16 * 5 // 16 + 1) * 8 / 16
    assert font.bold_offset == 0.5
    # 5.5 + 5.5 = 11; bold: + 0.5 each; rounded like Math.round
    assert font.string_width("aa") == 11
    assert font.string_width("a") == 6  # 5.5 -> 6
    assert font.string_width("§laa") == 12


def test_hd_only_for_big_cells() -> None:
    font = block_font(8, {"a": 5}, hd=True)
    assert font.char_width("a") == 6
    assert font.char_width(" ") == 4
    assert font.bold_offset == 1.0


def test_width_overrides() -> None:
    font = block_font(16, {"a": 9}, hd=True, widths={ord("a"): 3.25})
    assert font.char_width("a") == 3.25


def test_width_alpha_threshold() -> None:
    tex = np.zeros((128, 128, 4), np.uint8)
    tex[48:56, 8:12, 3] = 255  # "a": 4 ink columns
    tex[50, 12, 3] = 1  # a faint texel in column 5
    assert BitmapFont(tex).char_width("a") == 6
    assert BitmapFont(tex, ink_alpha=26).char_width("a") == 5


def test_parse_properties() -> None:
    text = "# comment\nwidth.33=2\nwidth.48 = 5.5\nblend=true\nwidth.300=4\nwidth.x=1\n"
    assert parse_width_properties(text) == {33: 2.0, 48: 5.5}


def test_hd_draw_advance() -> None:
    font = block_font(16, {"a": 9}, hd=True)
    c = Canvas(np.zeros((12, 40, 3), np.uint8), 2)
    assert draw_string(c, font, "§laa", 1, 1, 0xFFFFFF, shadow=False) == 12


def test_empty_glyph_width() -> None:
    font = block_font(ink={"a": 0})
    assert font.char_width("a") == 1


def test_bad_texture() -> None:
    with pytest.raises(ValueError):
        BitmapFont(np.zeros((128, 100, 4), np.uint8))


def test_string_width() -> None:
    font = block_font()  # 6 per char
    assert font.string_width("") == 0
    assert font.string_width("ab") == 12
    assert font.string_width("a b") == 16
    assert font.string_width("§9ab") == 12
    # bold adds 1 per char with a width
    assert font.string_width("§lab") == 14
    # a color code does not end bold in the width (1.8.9), only §r does
    assert font.string_width("§lB §9ab") == 7 + 5 + 14
    assert font.string_width("§lB §rab") == 7 + 5 + 12
    # a trailing § is a char of width -1
    assert font.string_width("a§") == 5


def render(font: BitmapFont, text: str, k: int = 1, w: int = 40) -> np.ndarray:
    c = Canvas(np.zeros((12 * k, w * k, 3), np.uint8), k)
    draw_string(c, font, text, 1, 1, 0xFFFFFF)
    return c.image()


def test_draw_plain_char() -> None:
    font = block_font(ink={"a": 2})
    img = render(font, "a")
    # shadow first at +1 +1, text on top
    assert (img[1:9, 1:3] == 255).all()
    assert (img[9, 2:4] == 0x3F).all()
    assert (img[2:10, 3] == 0x3F).all()
    assert (img[1, 3] == 0).all()


def test_draw_scaled() -> None:
    font = block_font(ink={"a": 2})
    img = render(font, "a", k=2)
    assert (img[2:18, 2:6] == 255).all()
    assert (img[18:20, 4:8] == 0x3F).all()


def test_draw_hd_font() -> None:
    # 16 texel cell, 4 texels ink = 2 GUI px; drawn at GUI scale 2: 1 texel per px
    font = block_font(16, {"a": 4})
    img = render(font, "a", k=2)
    assert (img[2:18, 2:6] == 255).all()
    assert (img[4:18, 6] == 0x3F).all()


def test_draw_colors_and_reset() -> None:
    font = block_font(ink={"a": 1})
    c = Canvas(np.zeros((12, 40, 3), np.uint8), 1)
    adv = draw_string(c, font, "§9a§ra", 1, 1, 0xFFFFFF, shadow=False)
    img = c.image()
    assert adv == 4
    assert tuple(img[1, 1]) == (0x55, 0x55, 0xFF)
    assert tuple(img[1, 3]) == (0xFF, 0xFF, 0xFF)


def test_draw_reset_swaps_blue_green() -> None:
    # 1.8.9 bug: §r sets the color as (red, blue, green)
    font = block_font(ink={"a": 1})
    c = Canvas(np.zeros((12, 40, 3), np.uint8), 1)
    draw_string(c, font, "§ra", 1, 1, 0x102030, shadow=False)
    assert tuple(c.image()[1, 1]) == (0x10, 0x30, 0x20)


def test_draw_bold() -> None:
    font = block_font(ink={"a": 1})
    c = Canvas(np.zeros((12, 40, 3), np.uint8), 1)
    adv = draw_string(c, font, "§la§9a", 1, 1, 0xFFFFFF, shadow=False)
    img = c.image()
    # bold: second copy at +1, advance + 1; the color code ends bold
    assert adv == 3 + 2
    assert (img[1, 1:3] == 255).all()
    assert tuple(img[1, 4]) == (0x55, 0x55, 0xFF)
    assert (img[1, 5] == 0).all()


def test_draw_italic() -> None:
    font = block_font(ink={"a": 1})
    c = Canvas(np.zeros((12, 40, 3), np.uint8), 1)
    draw_string(c, font, "§oa", 4, 1, 0xFFFFFF, shadow=False)
    img = c.image()
    # top row moves right by 1, bottom row left by 1
    assert (img[1, 5] == 255).all()
    assert (img[8, 3] == 255).all()


def test_draw_unknown_and_space() -> None:
    font = block_font(ink={"a": 1})
    c = Canvas(np.zeros((12, 40, 3), np.uint8), 1)
    adv = draw_string(c, font, "§ka aé§", 1, 1, 0xFFFFFF, shadow=False)
    # §k (obfuscated) is ignored; é has no glyph; a trailing § draws nothing
    assert adv == 2 + 4 + 2
    assert int(c.image().sum()) == 2 * 8 * 255 * 3


def test_ink_tint_multiplies() -> None:
    tex = np.zeros((128, 128, 4), np.uint8)
    tex[48:56, 8 * 1 : 8 * 1 + 1] = (128, 128, 128, 255)  # "a" = 97 = row 6 col 1
    font = BitmapFont(tex)
    c = Canvas(np.zeros((12, 40, 3), np.uint8), 1)
    draw_string(c, font, "a", 1, 1, 0xFF0000, shadow=False)
    assert tuple(c.image()[1, 1]) == (128, 0, 0)


def test_alpha_test_drops_faint_texels() -> None:
    tex = np.zeros((128, 128, 4), np.uint8)
    tex[48:56, 8] = (255, 255, 255, 20)  # alpha 20 / 255 < 0.1
    tex[48:56, 9] = (255, 255, 255, 128)
    font = BitmapFont(tex)
    c = Canvas(np.zeros((12, 40, 3), np.uint8), 1)
    draw_string(c, font, "a", 1, 1, 0xFFFFFF, shadow=False)
    img = c.image()
    assert (img[1, 1] == 0).all()
    assert (img[1, 2] == 128).all()  # blended: 255 * 128 / 255
