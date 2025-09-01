#!/usr/bin/env python3

import math
import sys
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from prism.calc import bedwars_level_from_exp
from prism.errors import (
    APIError,
    APIKeyError,
    APIThrottleError,
    PlayerNotFoundError,
)
from prism.hypixel import (
    HypixelAPIKeyHolder,
    MissingBedwarsStatsError,
    get_gamemode_stats,
    get_player_data,
)
from prism.mojang import get_uuid
from prism.utils import div, format_seconds, read_key, truncate_float

api_key = read_key(Path(sys.path[0]) / "api_key")
key_holder = HypixelAPIKeyHolder(api_key)


SEP = " " * 4

mode_prefixes = {
    "solo": "eight_one_",
    "doubles": "eight_two_",
    "threes": "four_three_",
    "fours": "four_four_",
    "overall": "",
}

mode_names = {
    "solo": "Solo",
    "doubles": "Doubles",
    "threes": "Threes",
    "fours": "Fours",
    "overall": "Overall",
}

stat_names = {
    "fks": "Finals",
    "fkdr": "FKDR",
    "wins": "Wins",
    "wlr": "WLR",
    "winstreak": "WS",
}

mode_order = ("solo", "doubles", "threes", "fours", "overall")
stat_order = ("fks", "fkdr", "wins", "wlr", "winstreak")
COLUMN_ORDER = ("mode_name", *stat_order)

assert set(mode_prefixes.keys()) == set(mode_names.keys()) == set(mode_order)
assert set(stat_names.keys()) == set(stat_order)


def get_sep(column: str) -> str:
    """Get the separator used in prints for this column"""
    return "\n" if column == COLUMN_ORDER[-1] else SEP


def div_string(dividend: float, divisor: float, decimals: int = 2) -> str:
    """Return the rounded answer to dividend/divisor as a string"""
    quotient = div(dividend, divisor)

    if not math.isfinite(quotient):
        return str(quotient)

    if isinstance(quotient, int):
        return str(quotient)

    return truncate_float(quotient, decimals)


def print_bedwars_stats(
    playerdata: Mapping[str, object], nick: str | None = None
) -> None:
    """Print a table of bedwars stats from the given player data"""
    try:
        bw_stats = cast(
            Mapping[str, Any], get_gamemode_stats(playerdata, gamemode="Bedwars")
        )
    except MissingBedwarsStatsError as e:
        # Player is missing stats in bedwars
        print(e)
        return

    stars = bedwars_level_from_exp(bw_stats.get("Experience", 500))

    displayname = playerdata.get("displayname", "<missing name>")
    nick_suffix = f" ({nick})" if nick is not None else ""
    print(f"{displayname}{nick_suffix} [{truncate_float(stars, 1)}]", end="")

    try:
        last_login = cast(int, playerdata["lastLogin"]) / 1000
        last_logout = cast(int, playerdata["lastLogout"]) / 1000
    except KeyError:
        # Privacy setting disabling access
        print()
    else:
        online = last_login > last_logout

        now = datetime.now().timestamp()
        time_since_login = now - last_login
        time_since_logout = now - last_logout

        print(
            f" - {'Online' if online else 'Offline'} "
            f"{format_seconds(time_since_login if online else time_since_logout)}"
        )

    table = {
        mode: {
            "fks": str(bw_stats.get(f"{prefix}final_kills_bedwars", 0)),
            "fkdr": div_string(
                bw_stats.get(f"{prefix}final_kills_bedwars", 0),
                bw_stats.get(f"{prefix}final_deaths_bedwars", 0),
            ),
            "wins": str(bw_stats.get(f"{prefix}wins_bedwars", 0)),
            "wlr": div_string(
                bw_stats.get(f"{prefix}wins_bedwars", 0),
                bw_stats.get(f"{prefix}games_played_bedwars", 0)
                - bw_stats.get(f"{prefix}wins_bedwars", 0),
            ),
            "winstreak": str(bw_stats.get(f"{prefix}winstreak", "-")),
            "mode_name": mode_names[mode],
        }
        for mode, prefix in mode_prefixes.items()
    }

    column_widths = {
        column: len(
            max(
                [
                    stat_names.get(column, ""),
                    *(table[mode][column] for mode in table.keys()),
                ],
                key=len,
            )
        )
        for column in COLUMN_ORDER
    }

    # Table header
    for column in COLUMN_ORDER:
        print(
            stat_names.get(column, "").ljust(column_widths[column]), end=get_sep(column)
        )

    for mode in mode_order:
        for column in COLUMN_ORDER:
            # Left justify the row label, right justify the cells
            justify = str.ljust if column == "mode_name" else str.rjust

            print(
                justify(table[mode].get(column, ""), column_widths[column]),
                end=get_sep(column),
            )


def get_and_display(username: str) -> None:
    try:
        uuid = get_uuid(username)
    except (APIError, PlayerNotFoundError):
        uuid = None

    if uuid is None:
        print(f"Could not find user with username {username}")
        return

    try:
        playerdata = get_player_data(uuid, key_holder)
    except (
        PlayerNotFoundError,
        APIError,
        APIKeyError,
        APIThrottleError,
    ) as e:
        print(e)
    else:
        print_bedwars_stats(playerdata, nick=None)


def main() -> None:
    for i, username in enumerate(sys.argv[1:]):
        get_and_display(username)

    while True:
        try:
            username = input("Username: ")
        except EOFError:
            print()
            break
        except KeyboardInterrupt:
            print()
            continue

        get_and_display(username)


if __name__ == "__main__":
    main()
