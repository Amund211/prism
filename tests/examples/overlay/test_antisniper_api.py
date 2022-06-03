from typing import Any

import pytest

from examples.overlay.antisniper_api import (
    MISSING_WINSTREAKS,
    Winstreaks,
    parse_estimated_winstreaks,
)


def make_winstreaks(
    overall: int | None = None,
    solo: int | None = None,
    doubles: int | None = None,
    threes: int | None = None,
    fours: int | None = None,
) -> Winstreaks:
    return Winstreaks(
        overall=overall, solo=solo, doubles=doubles, threes=threes, fours=fours
    )


assert MISSING_WINSTREAKS == make_winstreaks()

REAL_WINSTREAK_RESPONSE = {
    "success": True,
    "player": {
        "uuid": "some-uuid",
        "ign": "Player",
        "ign_lower": "player",
        "accurate": False,
        "date": 1654260069,
        "data": {
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
        },
    },
}


parse_estimated_winstreaks_cases: tuple[
    tuple[dict[str, Any], Winstreaks, bool], ...
] = (
    ({}, MISSING_WINSTREAKS, False),
    ({"success": False}, MISSING_WINSTREAKS, False),
    ({"success": True}, MISSING_WINSTREAKS, False),
    ({"success": True, "player": {}}, MISSING_WINSTREAKS, False),
    ({"success": True, "player": {"accurate": True}}, MISSING_WINSTREAKS, False),
    (
        {
            "player": {"accurate": True, "data": {"overall_winstreak": 19}},
        },
        MISSING_WINSTREAKS,
        False,
    ),
    # Passing cases
    (
        {
            "success": True,
            "player": {"accurate": True, "data": {"overall_winstreak": "what"}},
        },
        make_winstreaks(),
        True,
    ),
    (
        {"success": True, "player": {"accurate": True, "data": {}}},
        make_winstreaks(),
        True,
    ),
    (
        {"success": True, "player": {"accurate": True, "data": {}}},
        make_winstreaks(),
        True,
    ),
    (
        {
            "success": True,
            "player": {"accurate": True, "data": {"overall_winstreak": 19}},
        },
        make_winstreaks(overall=19),
        True,
    ),
    (
        REAL_WINSTREAK_RESPONSE,
        make_winstreaks(overall=10, solo=3, doubles=10, threes=15, fours=23),
        False,
    ),
)


@pytest.mark.parametrize(
    "response_json, winstreaks, winstreaks_accurate", parse_estimated_winstreaks_cases
)
def test_parse_estimated_winstreaks(
    response_json: dict[str, Any],
    winstreaks: Winstreaks,
    winstreaks_accurate: bool,
) -> None:
    assert parse_estimated_winstreaks(response_json) == (
        winstreaks,
        winstreaks_accurate,
    )
