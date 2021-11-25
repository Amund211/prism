"""
Search for /who responsed in the logfile and print the found users' stats

Example string printed to logfile when typing /who:
'[Info: 2021-10-29 15:29:33.059151572: GameCallbacks.cpp(162)] Game/net.minecraft.client.gui.GuiNewChat (Client thread) Info [CHAT] ONLINE: The_TOXIC__, T_T0xic, maskaom, NomexxD, Killerluise, Fruce_, 3Bitek, OhCradle, DanceMonky, Sweeetnesss, jbzn, squashypeas, Skydeaf, serocore'
"""

import os
import time
from dataclasses import dataclass
from typing import Sequence, Union, overload

from calc import bedwars_level_from_exp
from colors import Color
from playerdata import get_gamemode_stats, get_player_data
from utils import div

try:
    # A sequence of (lowecase) usernames that are assumed to be teammates
    # Teammates are sorted at the bottom of the stat list
    from customize import KNOWN_TEAMMATES
except ImportError:
    KNOWN_TEAMMATES: Sequence[str] = ()  # type: ignore[no-redef]


WHO_PREFIX = "Info [CHAT] ONLINE: "

assert all(username.islower() for username in KNOWN_TEAMMATES)


# Column separator
SEP = " " * 4


COLUMN_NAMES = {
    "IGN": "username",
    "Stars": "stars",
    "FKDR": "fkdr",
    "WLR": "wlr",
    "WS": "winstreak",
}


LEVEL_COLORMAP = (
    Color.LIGHT_GRAY,
    Color.LIGHT_WHITE,
    Color.YELLOW,
    Color.LIGHT_RED,
    Color.LIGHT_RED + Color.BG_WHITE,
)


STAT_LEVELS = {
    "stars": (100, 300, 500, 800),
    "fkdr": (0.5, 2, 4, 8),
    "wlr": (0.3, 1, 2, 4),
    "winstreak": (5, 15, 30, 50),
}

assert set(STAT_LEVELS.keys()).issubset(set(COLUMN_NAMES.values()))

# COLUMN_ORDER = ("IGN", "Stars", "FKDR", "WLR", "WS")
COLUMN_ORDER = ("IGN", "Stars", "FKDR", "WS")

assert set(COLUMN_ORDER).issubset(set(COLUMN_NAMES.keys()))


@dataclass(order=True)
class PlayerStats:
    """Dataclass holding the stats of a single player"""

    fkdr: float
    stars: float
    wlr: float
    winstreak: int
    username: str

    @property
    def nicked(self):
        """Return True if the player is assumed to be nicked"""
        return False

    def get_value(self, name: str) -> Union[int, float]:
        """Get the given stat from this player"""
        return getattr(self, name)

    def get_string(self, name: str) -> str:
        """Get a string representation of the given stat"""
        value = self.get_value(name)
        if isinstance(value, int):
            return str(value)
        elif isinstance(value, str):
            return value
        elif isinstance(value, float):
            return f"{value:.2f}"
        else:
            raise ValueError(f"{name=} {value=}")


@dataclass(order=True)
class NickedPlayer:
    """Dataclass holding the stats of a single player assumed to be nicked"""

    username: str

    @property
    def nicked(self):
        """Return True if the player is assumed to be nicked"""
        return True

    def get_value(self, name: str) -> Union[int, float]:
        """Get the given stat from this player (unknown in this case)"""
        return float("inf")

    def get_string(self, name: str) -> str:
        """Get a string representation of the given stat (unknown)"""
        return getattr(self, name, "unknown")


# Cache per session
KNOWN_STATS: dict[str, Union[PlayerStats, NickedPlayer]] = {}


def clear_screen():
    """Blank the screen"""
    os.system("cls" if os.name == "nt" else "clear")


def title(text):
    """Format the given text like a title (in bold)"""
    return Color.BOLD + text + Color.END


def color(
    text: str, value: Union[int, float], levels: Sequence[Union[int, float]]
) -> str:
    """
    Color the given text according to the thresholds in `levels`

    The level is computed as the smallest index i in levels that is such that
    value < levels[i]
    Alternatively the largest index i in levels such that
    value >= levels[i]

    This i is used to select the color from the global LEVEL_COLORMAP
    """

    assert len(levels) + 1 <= len(LEVEL_COLORMAP)

    for i, level in enumerate(levels):
        if value < level:
            break
    else:
        # Passed all levels
        i += 1

    color = LEVEL_COLORMAP[i]

    return color + text + Color.END


def get_bedwars_stats(username: str):
    """Print a table of bedwars stats from the given player data"""
    global KNOWN_STATS

    cached_stats = KNOWN_STATS.get(username, None)
    if cached_stats is not None:
        print(f"Cache hit {username}")
        return cached_stats

    print(f"Cache miss {username}")

    stats: Union[PlayerStats, NickedPlayer]

    try:
        playerdata = get_player_data(username)
    except (ValueError, RuntimeError) as e:
        # Assume the players is a nick
        print(f"Failed for {username}", e)
        stats = NickedPlayer(username=username)
    else:
        bw_stats = get_gamemode_stats(playerdata, gamemode="Bedwars")

        stats = PlayerStats(
            username=username,
            stars=bedwars_level_from_exp(bw_stats["Experience"]),
            fkdr=div(
                bw_stats["final_kills_bedwars"],
                bw_stats["final_deaths_bedwars"],
            ),
            wlr=div(
                bw_stats["wins_bedwars"],
                bw_stats["games_played_bedwars"] - bw_stats["wins_bedwars"],
            ),
            winstreak=bw_stats["winstreak"],
        )

    KNOWN_STATS[username] = stats

    return stats


@overload
def rate_stats(stats: PlayerStats) -> tuple[bool, bool, PlayerStats]:
    ...


@overload
def rate_stats(stats: NickedPlayer) -> tuple[bool, bool]:
    ...


def rate_stats(
    stats: Union[PlayerStats, NickedPlayer]
) -> Union[tuple[bool, bool], tuple[bool, bool, Union[PlayerStats, NickedPlayer]]]:
    """Used as a key function for sorting"""
    is_teammate = stats.username.lower() not in KNOWN_TEAMMATES
    if stats.nicked:
        return (is_teammate, stats.nicked)

    return (is_teammate, stats.nicked, stats)


def strip_who_prefix(line: str) -> str:
    """Remove the identifying prefix from a 'who' line"""
    return line[line.find(WHO_PREFIX) + len(WHO_PREFIX) :].strip()


def follow(thefile):
    thefile.seek(0, 2)
    while True:
        line = thefile.readline()
        if not line:
            time.sleep(0.01)
            continue
        yield line


def get_sep(column: str) -> str:
    """Get the separator used in prints for this column"""
    return "\n" if column == COLUMN_ORDER[-1] else SEP


def get_and_print(players: list[str]) -> None:
    stats = list(
        sorted(
            (get_bedwars_stats(player) for player in players),
            key=rate_stats,
            reverse=True,
        )
    )

    column_widths = {
        column: len(
            max((stat.get_string(COLUMN_NAMES[column]) for stat in stats), key=len)
        )
        for column in COLUMN_ORDER
    }

    clear_screen()

    # Table header
    for column in COLUMN_ORDER:
        print(title(column.ljust(column_widths[column])), end=get_sep(column))

    for stat in stats:
        for column in COLUMN_ORDER:
            # Left justify the username, right justify the cells
            justify = str.ljust if column == "IGN" else str.rjust

            stat_name = COLUMN_NAMES[column]

            levels = STAT_LEVELS.get(stat_name, None)

            stat_string = stat.get_string(stat_name)
            stat_value = stat.get_value(stat_name)

            if levels is None:
                final_string = stat_string
            else:
                final_string = color(stat_string, stat_value, levels)

            print(
                justify(
                    final_string,
                    column_widths[column] + (len(final_string) - len(stat_string)),
                ),
                end=get_sep(column),
            )


def watch_from_logfile(logpath: str) -> None:
    with open(logpath, "r") as logfile:
        loglines = follow(logfile)
        for line in loglines:
            if WHO_PREFIX in line:
                players = strip_who_prefix(line).split(", ")
                get_and_print(players)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Must provide a path to the logfile!", file=sys.stderr)
        sys.exit(1)

    watch_from_logfile(sys.argv[1])
