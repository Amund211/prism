import sys
from dataclasses import dataclass
from typing import Iterable, Iterator, Optional

from examples.sidelay.output.overlay_window import CellValue, OverlayRow, OverlayWindow
from examples.sidelay.output.utils import STAT_LEVELS
from examples.sidelay.parsing import parse_logline
from examples.sidelay.state import OverlayState, update_state
from examples.sidelay.stats import (
    NickedPlayer,
    Stats,
    get_bedwars_stats,
    rate_stats_for_non_party_members,
)

COLUMNS = ("username", "stars", "fkdr", "winstreak")
PRETTY_COLUMN_NAMES = {
    "username": "IGN",
    "stars": "Stars",
    "fkdr": "FKDR",
    "winstreak": "WS",
}

assert set(COLUMNS).issubset(set(STAT_LEVELS.keys()))
assert set(COLUMNS).issubset(set(PRETTY_COLUMN_NAMES.keys()))


def stats_to_row(stats: Stats) -> OverlayRow:
    """
    stat_string = stats.get_string(stat_name)
    stat_value = stats.get_value(stat_name)
    """

    return {
        "username": CellValue(stats.get_string("username"), "white"),
        "stars": CellValue(stats.get_string("stars"), "white"),
        "fkdr": CellValue(stats.get_string("fkdr"), "white"),
        "wlr": CellValue(stats.get_string("wlr"), "white"),
        "winstreak": CellValue(stats.get_string("winstreak"), "white"),
    }


@dataclass
class StateWrapper:
    """Wrapper storing the overlay state for use with tkinter"""

    state: OverlayState
    loglines: Iterator[str]
    api_key: str

    def get_new_stats(self) -> Optional[list[Stats]]:
        try:
            logline = next(self.loglines)
        except StopIteration:
            sys.exit(0)

        event = parse_logline(logline)

        if event is None:
            return None

        redraw = update_state(self.state, event)
        if not redraw:
            return None

        stats: list[Stats]
        TESTING = True  # TODO USE ACTUAL VARIABLE
        if TESTING:
            # No api requests in testing
            stats = [
                NickedPlayer(username=player) for player in self.state.lobby_players
            ]
        else:
            stats = [
                get_bedwars_stats(player, api_key=self.api_key)
                for player in self.state.lobby_players
            ]

        return stats


def process_loglines_to_overlay(
    state: OverlayState, loglines: Iterable[str], api_key: str
) -> None:
    wrapper = StateWrapper(state, iter(loglines), api_key)

    def get_new_rows() -> Optional[list[OverlayRow]]:
        new_stats = wrapper.get_new_stats()

        if new_stats is None:
            return None

        sorted_stats = list(
            sorted(
                new_stats,
                key=rate_stats_for_non_party_members(wrapper.state.party_members),
                reverse=True,
            )
        )

        return [stats_to_row(stats) for stats in sorted_stats]

    overlay = OverlayWindow(
        column_names=list(COLUMNS),
        pretty_column_names=PRETTY_COLUMN_NAMES,
        left_justified_columns={0},
        close_callback=lambda _: sys.exit(0),
        get_new_rows=get_new_rows,
    )
    overlay.run()
