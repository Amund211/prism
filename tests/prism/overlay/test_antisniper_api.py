from typing import Any

import pytest

from prism.overlay.antisniper_api import (
    AntiSniperAPIKeyHolder,
    Flag,
    get_denick_cache,
    parse_denick_response,
    parse_estimated_winstreaks_response,
    set_denick_cache,
)
from prism.overlay.player import MISSING_WINSTREAKS, Winstreaks
from tests.prism.overlay.utils import make_winstreaks

assert MISSING_WINSTREAKS == make_winstreaks()

REAL_DENICK_RESPONSE_SUCCESS = {
    "success": True,
    "player": {
        "uuid": "b70af64378b94854af6de83a2efd7e17",
        "dashed_uuid": "b70af643-78b9-4854-af6d-e83a2efd7e17",
        "nick_uuid": "ff62a260-e391-11ec-b541-e580d9c373b1",
        "dashed_nick_uuid": "ff62a260-e391-11ec-b541-e580d9c373b1",
        "date": 1654297687,
        "ign": "Voltey",
        "nick": "edater",
    },
}

REAL_DENICK_RESPONSE_FAIL = {"success": True, "player": None}

parse_denick_cases: tuple[tuple[dict[str, Any], str | None], ...] = (
    ({}, None),
    ({"success": False}, None),
    ({"success": True}, None),
    ({"success": True, "player": {}}, None),
    ({"success": True, "player": "invalidplayerdata"}, None),
    ({"player": {"uuid": "someuuid"}}, None),
    ({"success": False, "player": {"uuid": "someuuid"}}, None),
    (REAL_DENICK_RESPONSE_FAIL, None),
    # Passing cases
    ({"success": True, "player": {"uuid": "someuuid"}}, "someuuid"),
    (REAL_DENICK_RESPONSE_SUCCESS, "b70af64378b94854af6de83a2efd7e17"),
)


@pytest.mark.parametrize("response_json, uuid", parse_denick_cases)
def test_parse_denick_response(response_json: dict[str, Any], uuid: str | None) -> None:
    assert parse_denick_response(response_json) == uuid


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
    tuple[dict[str, Any], Winstreaks, bool], ...
] = (
    ({}, MISSING_WINSTREAKS, False),
    ({"success": False}, MISSING_WINSTREAKS, False),
    ({"success": True}, MISSING_WINSTREAKS, False),
    # Real response using a bogus name
    ({"success": True, "data": None}, MISSING_WINSTREAKS, False),
    ({"success": True, "overall_accurate": True}, MISSING_WINSTREAKS, True),
    (
        {"overall_accurate": True, "overall_winstreak": 19},
        MISSING_WINSTREAKS,
        False,
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
    ),
    (
        {"success": True, "overall_accurate": True},
        make_winstreaks(),
        True,
    ),
    (
        {"success": True, "overall_accurate": True, "overall_winstreak": 19},
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
def test_parse_estimated_winstreaks_response(
    response_json: dict[str, Any],
    winstreaks: Winstreaks,
    winstreaks_accurate: bool,
) -> None:
    assert parse_estimated_winstreaks_response(response_json) == (
        winstreaks,
        winstreaks_accurate,
    )


def test_set_get_cache() -> None:
    assert get_denick_cache("nonexistantentryinthecache") is Flag.NOT_SET
    assert get_denick_cache("mynewcacheentry12345") is Flag.NOT_SET
    assert get_denick_cache("mynewcacheentry123456") is Flag.NOT_SET

    assert set_denick_cache("mynewcacheentry12345", "value") == "value"
    assert get_denick_cache("mynewcacheentry12345") == "value"

    assert set_denick_cache("mynewcacheentry123456", None) is None
    assert get_denick_cache("mynewcacheentry123456") is None


def test_antisniper_key_holder() -> None:
    AntiSniperAPIKeyHolder(key="sdlfksjdflk", limit=10, window=1.5)
