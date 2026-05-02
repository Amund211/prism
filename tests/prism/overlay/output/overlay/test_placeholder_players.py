from prism.overlay.output.cell_renderer import render_stats
from prism.overlay.output.cells import GUI_COLORS
from prism.overlay.output.config import (
    DEFAULT_BBLR_CONFIG,
    DEFAULT_BEDS_CONFIG,
    DEFAULT_FINALS_CONFIG,
    DEFAULT_FKDR_CONFIG,
    DEFAULT_INDEX_CONFIG,
    DEFAULT_KDR_CONFIG,
    DEFAULT_KILLS_CONFIG,
    DEFAULT_SESSIONTIME_CONFIG,
    DEFAULT_STARS_CONFIG,
    DEFAULT_WINS_CONFIG,
    DEFAULT_WINSTREAK_CONFIG,
    DEFAULT_WLR_CONFIG,
    RatingConfigCollection,
)
from prism.overlay.output.overlay.placeholder_players import PLACEHOLDER_PLAYERS
from prism.player import KnownPlayer, NickedPlayer

DEFAULT_RATING_CONFIGS = RatingConfigCollection(
    stars=DEFAULT_STARS_CONFIG,
    index=DEFAULT_INDEX_CONFIG,
    fkdr=DEFAULT_FKDR_CONFIG,
    kdr=DEFAULT_KDR_CONFIG,
    bblr=DEFAULT_BBLR_CONFIG,
    wlr=DEFAULT_WLR_CONFIG,
    winstreak=DEFAULT_WINSTREAK_CONFIG,
    kills=DEFAULT_KILLS_CONFIG,
    finals=DEFAULT_FINALS_CONFIG,
    beds=DEFAULT_BEDS_CONFIG,
    wins=DEFAULT_WINS_CONFIG,
    sessiontime=DEFAULT_SESSIONTIME_CONFIG,
)


def test_placeholder_players_span_all_fkdr_tiers() -> None:
    """Each rating tier (5 colours) must be represented under default thresholds.

    If someone changes DEFAULT_FKDR_CONFIG so the placeholder values no longer
    span all tiers, the preview stops demonstrating every colour and this test
    catches it.
    """
    fkdr_colors = {
        render_stats(player, DEFAULT_RATING_CONFIGS).fkdr.color_sections[0].color
        for player in PLACEHOLDER_PLAYERS
        if isinstance(player, KnownPlayer)
    }
    assert fkdr_colors == set(
        GUI_COLORS
    ), f"Expected all 5 GUI_COLORS represented in fkdr, got {fkdr_colors}"


def test_placeholder_players_include_nicked_known_and_pure_nicked() -> None:
    """The preview must demo the edit-button enabled state.

    `player_to_row` enables the edit button for KnownPlayers with a nick set
    and for NickedPlayer instances. We need at least one of each.
    """
    has_nicked_known = any(
        isinstance(p, KnownPlayer) and p.nick is not None for p in PLACEHOLDER_PLAYERS
    )
    has_pure_nicked = any(isinstance(p, NickedPlayer) for p in PLACEHOLDER_PLAYERS)

    assert has_nicked_known, "Need a KnownPlayer with nick=... to demo edit-button"
    assert has_pure_nicked, "Need a NickedPlayer to demo the 'nick' placeholder cell"
