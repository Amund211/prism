from collections.abc import Mapping

import pytest

from prism.errors import APIError
from prism.overlay.antisniper_api import (
    STATS_ENDPOINT,
    AntiSniperWinstreakProvider,
    StrangePlayerProvider,
    parse_estimated_winstreaks_response,
)
from prism.player import MISSING_WINSTREAKS, Winstreaks
from tests.prism.overlay.utils import make_winstreaks

assert MISSING_WINSTREAKS == make_winstreaks()

REAL_WINSTREAK_RESPONSE = {
    "success": True,
    "uuid": "some-uuid",
    "ign": "Player",
    "hidden": True,
    "overall_accurate": False,
    "last_accuracy_checked": 1678380984,
    "last_check_time": 1678380983000,
    "overall_winstreak": 10,
    "eight_one_winstreak": 3,
    "eight_two_winstreak": 10,
    "four_three_winstreak": 15,
    "four_four_winstreak": 23,
    "two_four_winstreak": 5,
    "castle_winstreak": 0,
    "eight_one_rush_winstreak": 0,
    "eight_two_rush_winstreak": 0,
    "four_four_rush_winstreak": 3,
    "eight_one_ultimate_winstreak": 0,
    "eight_two_ultimate_winstreak": 1,
    "four_four_ultimate_winstreak": 2,
    "eight_two_armed_winstreak": 1,
    "four_four_armed_winstreak": 1,
    "eight_two_lucky_winstreak": 7,
    "four_four_lucky_winstreak": 1,
    "eight_two_voidless_winstreak": 1,
    "four_four_voidless_winstreak": 3,
    "tourney_bedwars_two_four_0_winstreak": 11,
    "tourney_bedwars4s_0_winstreak": 6,
    "tourney_bedwars4s_1_winstreak": 2,
    "eight_two_underworld_winstreak": 0,
    "four_four_underworld_winstreak": 1,
    "eight_two_swap_winstreak": 1,
    "four_four_swap_winstreak": 1,
}


parse_estimated_winstreaks_cases: tuple[
    tuple[Mapping[str, object], Winstreaks, bool, type[Exception] | None], ...
] = (
    ({}, MISSING_WINSTREAKS, False, APIError),
    ({"success": False}, MISSING_WINSTREAKS, False, APIError),
    ({"success": True}, MISSING_WINSTREAKS, False, None),
    # Real response using a bogus name
    ({"success": True, "data": None}, MISSING_WINSTREAKS, False, None),
    ({"success": True, "overall_accurate": True}, MISSING_WINSTREAKS, True, None),
    (
        {"overall_accurate": True, "overall_winstreak": 19},
        MISSING_WINSTREAKS,
        False,
        APIError,
    ),
    # Passing cases
    (
        {
            "success": True,
            "overall_accurate": True,
            "overall_winstreak": "what",
        },
        make_winstreaks(),
        True,
        None,
    ),
    (
        {"success": True, "overall_accurate": True},
        make_winstreaks(),
        True,
        None,
    ),
    (
        {"success": True, "overall_accurate": True, "overall_winstreak": 19},
        make_winstreaks(overall=19),
        True,
        None,
    ),
    (
        REAL_WINSTREAK_RESPONSE,
        make_winstreaks(overall=10, solo=3, doubles=10, threes=15, fours=23),
        False,
        None,
    ),
)


@pytest.mark.parametrize(
    "response_json, winstreaks, winstreaks_accurate, error",
    parse_estimated_winstreaks_cases,
)
def test_parse_estimated_winstreaks_response(
    response_json: Mapping[str, object],
    winstreaks: Winstreaks,
    winstreaks_accurate: bool,
    error: type[Exception] | None,
) -> None:
    if error is not None:
        with pytest.raises(error):
            parse_estimated_winstreaks_response(response_json)
        return

    # We now treat winstreak estimates from antisniper as inaccurate
    winstreaks_accurate = False
    assert parse_estimated_winstreaks_response(response_json) == (
        winstreaks,
        winstreaks_accurate,
    )


def test_stats_endpoint() -> None:
    # Make sure we don't release a version using the test endpoint
    assert STATS_ENDPOINT == "https://flashlight.recdep.no"


def test_strange_player_provider() -> None:
    provider = StrangePlayerProvider(
        retry_limit=3, initial_timeout=1.0, get_time_ns=lambda: 1234567890123456789
    )
    assert provider.seconds_until_unblocked == 0.0


def test_antisniper_winstreak_provider() -> None:
    provider = AntiSniperWinstreakProvider(retry_limit=3, initial_timeout=1.0)
    assert provider.seconds_until_unblocked == 0.0
