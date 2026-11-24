import re

import numpy as np

from synth.tablist import TabSpec, render
from synth.variety import (
    TEAMS,
    Options,
    random_badge,
    random_head,
    random_icon,
    random_name,
    random_spec,
    random_style,
)
from tests.helpers import block_font

NAME = re.compile(r"^[A-Za-z0-9_]{3,16}$")


def test_names() -> None:
    rng = np.random.default_rng(1)
    for _ in range(200):
        assert NAME.match(random_name(rng))


def test_sprites() -> None:
    rng = np.random.default_rng(2)
    head = random_head(rng)
    assert head.texels.shape == (8, 8, 4) and (head.texels[..., 3] == 255).all()
    icon = random_icon(rng, 4)
    assert icon.texels.shape == (32, 32, 4) and (icon.gui_w, icon.gui_h) == (8, 8)
    assert 0 < (icon.texels[..., 3] > 0).mean() < 1
    badge = random_badge(rng, 2)
    assert badge.texels.shape == (16, 16, 4)
    assert 0 < (badge.texels[..., 3] > 0).mean() < 1


def test_spec_deterministic() -> None:
    a = random_spec(np.random.default_rng(3), Options())
    b = random_spec(np.random.default_rng(3), Options())
    assert [r.text for r in a.rows] == [r.text for r in b.rows]


def test_spec_content() -> None:
    rng = np.random.default_rng(4)
    opts = Options(
        min_rows=12,
        max_rows=12,
        p_icon=1.0,
        p_badge=1.0,
        p_spectator=0.0,
        p_no_team=0.0,
    )
    spec = random_spec(rng, opts)
    assert len(spec.rows) == 12
    letters = {t[0] for t in TEAMS.values()}
    for r in spec.rows:
        assert r.icon is not None and r.badge is not None and r.head is not None
        m = re.match(r"^§(.)§l(.) §\1(.+)$", r.text)
        assert m and m.group(2) in letters and NAME.match(m.group(3))
    # rows are grouped by team
    teams = [r.text[:2] for r in spec.rows]
    assert teams == sorted(teams, key=teams.index)


def test_spec_no_team_rows() -> None:
    # Respawning / eliminated players (Forge and Lunar captures): gray or white
    # name, no team letter, not italic, score shown like a normal row.
    rng = np.random.default_rng(9)
    opts = Options(min_rows=16, max_rows=16, p_no_team=1.0, p_spectator=0.0)
    texts = []
    for _ in range(20):
        spec = random_spec(rng, opts)
        assert spec.rows
        for r in spec.rows:
            m = re.match(r"^§([7f])(.+)$", r.text)
            assert m and NAME.match(m.group(2)) and not r.spectator
            texts.append(r.text[:2])
    assert set(texts) == {"§7", "§f"}
    assert texts.count("§7") > texts.count("§f")


def test_spec_no_team_keeps_place() -> None:
    rng = np.random.default_rng(10)
    opts = Options(min_rows=16, max_rows=16, p_no_team=0.5, p_spectator=0.0)
    spec = random_spec(rng, opts)
    kinds = {r.text[:2] for r in spec.rows}
    assert {"§7", "§f"} & kinds and len(kinds) > 2


def test_spec_options_off() -> None:
    rng = np.random.default_rng(5)
    opts = Options(p_icon=0.0, p_badge=0.0, p_spectator=1.0, p_score=0.0, p_header=0.0)
    spec = random_spec(rng, opts)
    assert spec.header == () and spec.footer == () and not spec.score
    assert all(r.spectator and r.icon is None and r.badge is None for r in spec.rows)
    assert all(not r.text.startswith("§") for r in spec.rows)


def test_spec_header_footer() -> None:
    spec = random_spec(np.random.default_rng(6), Options(p_header=1.0))
    assert len(spec.header) >= 1 and len(spec.footer) >= 1


def test_style() -> None:
    rng = np.random.default_rng(7)
    styles = [random_style(rng) for _ in range(50)]
    assert {s.slot_over_box for s in styles} == {True, False}
    assert {s.heads for s in styles} == {True, False}
    assert {s.ping for s in styles} == {True, False}


def test_renders() -> None:
    rng = np.random.default_rng(8)
    bg = (rng.random((540, 960, 3)) * 255).astype(np.uint8)
    for _ in range(5):
        spec = random_spec(rng, Options())
        res = render(bg, spec, block_font(), 1, random_style(rng))
        assert res.ink.any()
        assert isinstance(spec, TabSpec)
