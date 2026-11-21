import numpy as np
import pytest

from prism.overlay.tabcap.synth.canvas import Canvas, Sprite


def test_gui_size() -> None:
    c = Canvas(np.zeros((1080, 1920, 3), np.uint8), 2)
    assert (c.gui_width, c.gui_height) == (960, 540)
    c = Canvas(np.zeros((1080, 1921, 3), np.uint8), 2)
    assert c.gui_width == 961  # ceil, as ScaledResolution


def test_fill_rect_rounds_once() -> None:
    bg = np.arange(256, dtype=np.uint8).repeat(3).reshape(16, 16, 3)
    c = Canvas(bg, 1)
    c.fill_rect(0, 0, 16, 16, 0x000000, 128)
    c.fill_rect(0, 0, 16, 16, 0x000000, 32)
    v = bg.astype(float) * 127 / 255 * 223 / 255
    assert (c.image() == np.floor(v + 0.5)).all()


def test_fill_rect_over_background() -> None:
    c = Canvas(np.full((2, 2, 3), 200, np.uint8), 1)
    c.fill_rect(0, 0, 2, 2, 0x000000, 128)
    c.fill_rect(0, 0, 1, 2, 0x000000, 144, over_background=True)
    img = c.image()
    assert (img[:, 0] == int(np.floor(200 * 111 / 255 + 0.5))).all()
    assert (img[:, 1] == int(np.floor(200 * 127 / 255 + 0.5))).all()


def test_fill_rect_scaled_and_clipped() -> None:
    c = Canvas(np.zeros((4, 6, 3), np.uint8), 2)
    c.fill_rect(1, 0, 5, 1, 0xFFFFFF, 255)
    img = c.image()
    assert (img[0:2, 2:6] == 255).all()
    assert (img[0:2, 0:2] == 0).all()
    assert (img[2:4] == 0).all()


def test_blit_sprite_nearest() -> None:
    tex = np.zeros((2, 2, 4), np.uint8)
    tex[0, 0] = (255, 0, 0, 255)
    tex[1, 1] = (0, 0, 255, 255)
    c = Canvas(np.zeros((8, 8, 3), np.uint8), 2)
    c.blit(Sprite(tex, 2, 2), 1, 1)
    img = c.image()
    assert tuple(img[2, 2]) == (255, 0, 0)
    assert tuple(img[3, 3]) == (255, 0, 0)
    assert tuple(img[5, 5]) == (0, 0, 255)
    assert tuple(img[2, 5]) == (0, 0, 0)  # alpha 0: not drawn
    assert c.ink[2, 2] and c.ink[5, 5] and not c.ink[2, 5]
    assert int(c.ink.sum()) == 8


def test_blit_hires_sprite() -> None:
    # 4x4 texels on 2x2 GUI px at scale 2: one texel per screen px
    tex = np.zeros((4, 4, 4), np.uint8)
    tex[..., 3] = 255
    tex[1, 2, :3] = 200
    c = Canvas(np.zeros((4, 4, 3), np.uint8), 2)
    c.blit(Sprite(tex, 2, 2), 0, 0)
    img = c.image()
    assert tuple(img[1, 2]) == (200, 200, 200)
    assert int(img.sum()) == 600


def test_blit_blends_alpha() -> None:
    tex = np.full((1, 1, 4), 255, np.uint8)
    tex[0, 0, 3] = 51
    c = Canvas(np.full((1, 1, 3), 100, np.uint8), 1)
    c.blit(Sprite(tex, 1, 1), 0, 0)
    assert tuple(c.image()[0, 0]) == (131, 131, 131)  # 255 * 0.2 + 100 * 0.8


def test_blit_off_screen() -> None:
    tex = np.full((1, 1, 4), 255, np.uint8)
    c = Canvas(np.zeros((2, 2, 3), np.uint8), 1)
    c.blit(Sprite(tex, 1, 1), 5, 5)
    c.blit(Sprite(tex, 1, 1), -3, 0)
    assert int(c.image().sum()) == 0


def test_bad_inputs() -> None:
    with pytest.raises(ValueError):
        Canvas(np.zeros((2, 2), np.uint8), 1)
    with pytest.raises(ValueError):
        Canvas(np.zeros((2, 2, 3), np.uint8), 0)
    with pytest.raises(ValueError):
        Sprite(np.zeros((2, 2, 3), np.uint8), 1, 1)
