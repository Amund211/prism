import unittest.mock

from prism.overlay.output.cells import GUI_COLORS, CellValue, ColorSection
from prism.overlay.output.overlay.team_danger_strip_controller import (
    TeamDangerStripController,
    format_lobby_danger_banner,
)
from prism.overlay.team_types import (
    TEAM_MINECRAFT_COLORS,
    DangerTier,
    LobbyDangerSummary,
    PlayerDanger,
    PlayerStatStatus,
    RecommendationPhase,
    TeamColor,
    TeamDangerBannerData,
    TeamDangerSummary,
    danger_tier_to_gui_color,
)


def _make_team(
    team: TeamColor = "red",
    danger_score: float = 120.0,
    tier: DangerTier = "medium",
    alive_count: int = 3,
    top_player: str | None = "Player1",
    pending_count: int = 0,
    unknown_count: int = 0,
    is_own_team: bool = False,
) -> TeamDangerSummary:
    return TeamDangerSummary(
        team=team,
        danger_score=danger_score,
        total_player_danger=danger_score,
        peak_player_danger=danger_score,
        tier=tier,
        alive_count=alive_count,
        known_or_nicked_count=max(0, alive_count - pending_count - unknown_count),
        pending_count=pending_count,
        unknown_count=unknown_count,
        top_player=top_player,
        is_own_team=is_own_team,
    )


def _make_player(
    username: str = "Player1",
    danger_score: float = 50.0,
    status: PlayerStatStatus = "known",
    tier: DangerTier = "low",
) -> PlayerDanger:
    return PlayerDanger(
        username=username,
        danger_score=danger_score,
        status=status,
        tier=tier,
        team=None,
    )


def _make_summary(
    phase: RecommendationPhase = "opening",
    enemy_teams: tuple[TeamDangerSummary, ...] = (),
    own_team: TeamDangerSummary | None = None,
    priority_target: TeamDangerSummary | None = None,
    unassigned_enemies: tuple[PlayerDanger, ...] = (),
    pending_enemy_count: int = 0,
    unknown_enemy_count: int = 0,
) -> LobbyDangerSummary:
    return LobbyDangerSummary(
        phase=phase,
        enemy_teams=enemy_teams,
        own_team=own_team,
        priority_target=priority_target,
        unassigned_enemies=unassigned_enemies,
        pending_enemy_count=pending_enemy_count,
        unknown_enemy_count=unknown_enemy_count,
    )


def test_controller_initialization_and_tick_diffing() -> None:
    set_banner_mock = unittest.mock.MagicMock()
    controller = TeamDangerStripController.create(set_banner=set_banner_mock)

    assert controller.last_banner is None
    set_banner_mock.assert_not_called()

    # Ticking None initially is a no-op (last_banner is already None)
    controller.tick(None)
    set_banner_mock.assert_not_called()

    # Ticking a banner invokes set_banner
    banner1 = TeamDangerBannerData(
        headline=CellValue.monochrome("test1", GUI_COLORS[0]),
        team_summary_line=None,
    )
    controller.tick(banner1)
    set_banner_mock.assert_called_once_with(banner1)
    assert controller.last_banner == banner1

    # Identical banner is a no-op
    set_banner_mock.reset_mock()
    controller.tick(banner1)
    set_banner_mock.assert_not_called()

    # Updating with a different banner invokes set_banner
    banner2 = TeamDangerBannerData(
        headline=CellValue.monochrome("test2", GUI_COLORS[1]),
        team_summary_line=None,
    )
    controller.tick(banner2)
    set_banner_mock.assert_called_once_with(banner2)
    assert controller.last_banner == banner2

    # Setting banner back to None calls set_banner(None)
    set_banner_mock.reset_mock()
    controller.tick(None)
    set_banner_mock.assert_called_once_with(None)
    assert controller.last_banner is None

    # Ticking None again is a no-op
    set_banner_mock.reset_mock()
    controller.tick(None)
    set_banner_mock.assert_not_called()


def test_format_lobby_danger_banner_none_or_empty() -> None:
    assert format_lobby_danger_banner(None) is None

    empty_summary = _make_summary(
        enemy_teams=(),
        unassigned_enemies=(),
    )
    assert format_lobby_danger_banner(empty_summary) is None


def test_headline_case_a_pending_stats() -> None:
    unassigned = (_make_player("Player1", status="pending", tier="pending"),)
    summary = _make_summary(
        pending_enemy_count=3,
        unassigned_enemies=unassigned,
    )

    banner = format_lobby_danger_banner(summary)
    assert banner is not None
    assert banner.headline == CellValue.monochrome(
        "TEAM DANGER: Loading enemy stats (3 pending)...",
        GUI_COLORS[0],
    )
    assert banner.team_summary_line is None


def test_headline_case_b_opening_phase_with_top_player() -> None:
    target = _make_team(
        team="red",
        danger_score=150.0,
        tier="medium",
        alive_count=3,
        top_player="Player1",
    )
    summary = _make_summary(
        phase="opening",
        enemy_teams=(target,),
        priority_target=target,
    )

    banner = format_lobby_danger_banner(summary)
    assert banner is not None

    prefix = "OPENING TARGET (STATS): "
    badge = "[RED]"
    details = " Danger 150 (3 alive, Carry: Player1)"

    assert banner.headline.text == f"{prefix}{badge}{details}"
    assert banner.headline.color_sections == (
        ColorSection(GUI_COLORS[1], len(prefix)),
        ColorSection(TEAM_MINECRAFT_COLORS["red"], len(badge)),
        ColorSection(danger_tier_to_gui_color("medium"), len(details)),
    )


def test_headline_case_b_midgame_phase_without_top_player() -> None:
    target = _make_team(
        team="blue",
        danger_score=210.0,
        tier="high",
        alive_count=2,
        top_player=None,
    )
    summary = _make_summary(
        phase="midgame",
        enemy_teams=(target,),
        priority_target=target,
    )

    banner = format_lobby_danger_banner(summary)
    assert banner is not None

    prefix = "TOP ALIVE THREAT: "
    badge = "[BLUE]"
    details = " Danger 210 (2 alive)"

    assert banner.headline.text == f"{prefix}{badge}{details}"
    assert banner.headline.color_sections == (
        ColorSection(GUI_COLORS[1], len(prefix)),
        ColorSection(TEAM_MINECRAFT_COLORS["blue"], len(badge)),
        ColorSection(danger_tier_to_gui_color("high"), len(details)),
    )


def test_headline_case_c_unassigned_known_and_nicked() -> None:
    known_player = _make_player(
        "Player2",
        danger_score=75.0,
        status="known",
        tier="low",
    )
    summary_known = _make_summary(
        unassigned_enemies=(known_player,),
    )

    banner_known = format_lobby_danger_banner(summary_known)
    assert banner_known is not None

    prefix = "TOP UNASSIGNED THREAT: "
    player_text = "Player2 (Danger 75)"
    suffix = " | /w !r=Name sets team"

    assert banner_known.headline.text == f"{prefix}{player_text}{suffix}"
    assert banner_known.headline.color_sections == (
        ColorSection(GUI_COLORS[1], len(prefix)),
        ColorSection(danger_tier_to_gui_color("low"), len(player_text)),
        ColorSection(GUI_COLORS[0], len(suffix)),
    )

    nicked_player = _make_player(
        "Player3",
        danger_score=65.0,
        status="nicked",
        tier="low",
    )
    summary_nicked = _make_summary(
        unassigned_enemies=(nicked_player,),
    )

    banner_nicked = format_lobby_danger_banner(summary_nicked)
    assert banner_nicked is not None
    assert banner_nicked.headline.text == (
        "TOP UNASSIGNED THREAT: Player3 (Danger 65) | /w !r=Name sets team"
    )


def test_headline_case_c_only_unknown_unassigned_or_no_eligible() -> None:
    unknown_player = _make_player(
        "Player4",
        danger_score=0.0,
        status="unknown",
        tier="unknown",
    )
    summary_unknown = _make_summary(
        unassigned_enemies=(unknown_player,),
    )

    banner_unknown = format_lobby_danger_banner(summary_unknown)
    assert banner_unknown is not None
    assert banner_unknown.headline == CellValue.monochrome(
        "TEAM DANGER: Enemy stats unavailable (error)",
        GUI_COLORS[0],
    )

    unknown_team = _make_team(
        team="green",
        danger_score=0.0,
        tier="unknown",
        alive_count=2,
        unknown_count=2,
    )
    summary_no_eligible = _make_summary(
        enemy_teams=(unknown_team,),
        priority_target=None,
        pending_enemy_count=0,
        unassigned_enemies=(),
    )

    banner_no_eligible = format_lobby_danger_banner(summary_no_eligible)
    assert banner_no_eligible is not None
    assert banner_no_eligible.headline == CellValue.monochrome(
        "TEAM DANGER: Enemy stats unavailable (error)",
        GUI_COLORS[0],
    )


def test_team_summary_line_single_team() -> None:
    team = _make_team(
        team="yellow",
        danger_score=95.0,
        tier="low",
        alive_count=4,
    )
    summary = _make_summary(
        enemy_teams=(team,),
        priority_target=team,
    )

    banner = format_lobby_danger_banner(summary)
    assert banner is not None
    assert banner.team_summary_line is not None

    expected_badge = "[YELLOW]"
    expected_score = " 95 (4)"
    assert banner.team_summary_line.text == f"{expected_badge}{expected_score}"
    assert banner.team_summary_line.color_sections == (
        ColorSection(TEAM_MINECRAFT_COLORS["yellow"], len(expected_badge)),
        ColorSection(danger_tier_to_gui_color("low"), len(expected_score)),
    )


def test_team_summary_line_multiple_teams_with_indicators_and_unassigned() -> None:
    team_red = _make_team(
        team="red",
        danger_score=160.0,
        tier="medium",
        alive_count=3,
        pending_count=1,
    )
    team_blue = _make_team(
        team="blue",
        danger_score=110.0,
        tier="medium",
        alive_count=4,
        unknown_count=2,
    )
    team_green = _make_team(
        team="green",
        danger_score=310.0,
        tier="extreme",
        alive_count=2,
    )

    unassigned = (
        _make_player("Player1", danger_score=40.0),
        _make_player("Player2", danger_score=50.0),
    )

    summary = _make_summary(
        enemy_teams=(team_red, team_blue, team_green),
        priority_target=team_green,
        unassigned_enemies=unassigned,
    )

    banner = format_lobby_danger_banner(summary)
    assert banner is not None
    assert banner.team_summary_line is not None

    expected_text = (
        "[RED] 160* (3)   [BLUE] 110? (4)   [GREEN] 310 (2)   [UNASSIGNED] 2"
    )
    assert banner.team_summary_line.text == expected_text

    assert banner.team_summary_line.color_sections == (
        ColorSection(TEAM_MINECRAFT_COLORS["red"], len("[RED]")),
        ColorSection(danger_tier_to_gui_color("medium"), len(" 160* (3)")),
        ColorSection(GUI_COLORS[0], len("   ")),
        ColorSection(TEAM_MINECRAFT_COLORS["blue"], len("[BLUE]")),
        ColorSection(danger_tier_to_gui_color("medium"), len(" 110? (4)")),
        ColorSection(GUI_COLORS[0], len("   ")),
        ColorSection(TEAM_MINECRAFT_COLORS["green"], len("[GREEN]")),
        ColorSection(danger_tier_to_gui_color("extreme"), len(" 310 (2)")),
        ColorSection(GUI_COLORS[0], len("   [UNASSIGNED] 2")),
    )
