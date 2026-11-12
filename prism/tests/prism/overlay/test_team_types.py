from dataclasses import FrozenInstanceError
from typing import cast

import pytest

from prism.overlay.output.cells import GUI_COLORS, CellValue
from prism.overlay.output.color import MinecraftColor
from prism.overlay.team_types import (
    ALL_TEAM_COLORS,
    TEAM_ALIAS_MAP,
    TEAM_DISPLAY_NAMES,
    TEAM_MINECRAFT_COLORS,
    TEAM_ORDER_INDEX,
    TEAM_SHORT_LABELS,
    DangerTier,
    LobbyDangerSummary,
    PlayerDanger,
    TeamColor,
    TeamDangerBannerData,
    TeamDangerSummary,
    danger_tier_to_gui_color,
    str_is_team_color,
)


def test_team_constants() -> None:
    expected_colors: tuple[TeamColor, ...] = ("red", "blue", "green", "yellow")
    assert ALL_TEAM_COLORS == expected_colors

    assert TEAM_ORDER_INDEX == {
        "red": 0,
        "blue": 1,
        "green": 2,
        "yellow": 3,
    }

    assert TEAM_DISPLAY_NAMES == {
        "red": "RED",
        "blue": "BLUE",
        "green": "GREEN",
        "yellow": "YELLOW",
    }

    assert TEAM_SHORT_LABELS == {
        "red": "R",
        "blue": "B",
        "green": "G",
        "yellow": "Y",
    }

    assert TEAM_MINECRAFT_COLORS == {
        "red": MinecraftColor.RED,
        "blue": MinecraftColor.BLUE,
        "green": MinecraftColor.GREEN,
        "yellow": MinecraftColor.YELLOW,
    }

    assert TEAM_ALIAS_MAP == {
        "red": "red",
        "r": "red",
        "blue": "blue",
        "b": "blue",
        "green": "green",
        "g": "green",
        "yellow": "yellow",
        "y": "yellow",
    }


@pytest.mark.parametrize(
    "raw_val, expected",
    [
        ("red", True),
        ("blue", True),
        ("green", True),
        ("yellow", True),
        ("RED", False),
        ("purple", False),
        ("r", False),
        ("blue ", False),
        ("", False),
    ],
)
def test_str_is_team_color(raw_val: str, expected: bool) -> None:
    assert str_is_team_color(raw_val) is expected


@pytest.mark.parametrize(
    "tier, expected_color",
    [
        ("pending", GUI_COLORS[0]),
        ("unknown", GUI_COLORS[0]),
        ("low", GUI_COLORS[1]),
        ("medium", GUI_COLORS[2]),
        ("high", GUI_COLORS[3]),
        ("extreme", GUI_COLORS[4]),
    ],
)
def test_danger_tier_to_gui_color(tier: DangerTier, expected_color: str) -> None:
    assert danger_tier_to_gui_color(tier) == expected_color


def test_danger_tier_to_gui_color_invalid() -> None:
    with pytest.raises(AssertionError):
        danger_tier_to_gui_color(cast(DangerTier, "invalid_tier"))


def test_player_danger_dataclass() -> None:
    pd = PlayerDanger(
        username="Player1",
        danger_score=125.5,
        status="known",
        tier="medium",
        team="red",
    )
    assert pd.username == "Player1"
    assert pd.danger_score == 125.5
    assert pd.status == "known"
    assert pd.tier == "medium"
    assert pd.team == "red"

    with pytest.raises(FrozenInstanceError):
        pd.username = "Player2"  # type: ignore[misc]


@pytest.mark.parametrize(
    (
        "is_own_team",
        "alive_count",
        "pending_count",
        "known_or_nicked_count",
        "expected_eligible",
    ),
    [
        # Own team is never eligible
        (True, 4, 0, 4, False),
        # Dead enemy team is not eligible
        (False, 0, 0, 4, False),
        # Team with pending stats is not eligible
        (False, 4, 1, 3, False),
        # Team with 0 known or nicked players (all unknown) is not eligible
        (False, 4, 0, 0, False),
        # Valid enemy team with known/nicked players is eligible
        (False, 4, 0, 4, True),
        # Valid enemy team with mixed known and unknown players is eligible
        (False, 4, 0, 2, True),
    ],
)
def test_team_danger_summary_eligibility(
    is_own_team: bool,
    alive_count: int,
    pending_count: int,
    known_or_nicked_count: int,
    expected_eligible: bool,
) -> None:
    summary = TeamDangerSummary(
        team="blue",
        danger_score=210.0,
        total_player_danger=180.0,
        peak_player_danger=110.0,
        tier="high",
        alive_count=alive_count,
        known_or_nicked_count=known_or_nicked_count,
        pending_count=pending_count,
        unknown_count=alive_count - (known_or_nicked_count + pending_count),
        top_player="Player1",
        is_own_team=is_own_team,
    )
    assert summary.is_eligible_target is expected_eligible

    with pytest.raises(FrozenInstanceError):
        summary.danger_score = 999.0  # type: ignore[misc]


def test_lobby_danger_summary_dataclass() -> None:
    own = TeamDangerSummary(
        team="red",
        danger_score=50.0,
        total_player_danger=50.0,
        peak_player_danger=25.0,
        tier="low",
        alive_count=4,
        known_or_nicked_count=4,
        pending_count=0,
        unknown_count=0,
        top_player="Me",
        is_own_team=True,
    )
    enemy = TeamDangerSummary(
        team="blue",
        danger_score=350.0,
        total_player_danger=300.0,
        peak_player_danger=150.0,
        tier="extreme",
        alive_count=4,
        known_or_nicked_count=4,
        pending_count=0,
        unknown_count=0,
        top_player="Player1",
        is_own_team=False,
    )
    unassigned = PlayerDanger(
        username="Player2",
        danger_score=0.0,
        status="pending",
        tier="pending",
        team=None,
    )
    lobby = LobbyDangerSummary(
        phase="opening",
        enemy_teams=(enemy,),
        own_team=own,
        priority_target=enemy,
        unassigned_enemies=(unassigned,),
        pending_enemy_count=1,
        unknown_enemy_count=0,
    )
    assert lobby.phase == "opening"
    assert lobby.enemy_teams == (enemy,)
    assert lobby.own_team == own
    assert lobby.priority_target == enemy
    assert lobby.unassigned_enemies == (unassigned,)
    assert lobby.pending_enemy_count == 1
    assert lobby.unknown_enemy_count == 0

    with pytest.raises(FrozenInstanceError):
        lobby.phase = "midgame"  # type: ignore[misc]


def test_team_danger_banner_data_dataclass() -> None:
    headline = CellValue.monochrome("PRIORITY TARGET: BLUE", GUI_COLORS[4])
    summary_line = CellValue.monochrome("R: 50 | B: 350 | G: - | Y: -", GUI_COLORS[1])
    banner = TeamDangerBannerData(
        headline=headline,
        team_summary_line=summary_line,
    )
    assert banner.headline == headline
    assert banner.headline_prefix == "PRIORITY TARGET: BLUE"
    assert banner.team_summary_line == summary_line

    banner_none = TeamDangerBannerData(
        headline=headline,
        team_summary_line=None,
    )
    assert banner_none.team_summary_line is None

    with pytest.raises(FrozenInstanceError):
        banner.headline = headline  # type: ignore[misc]
