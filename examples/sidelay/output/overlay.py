import sys
from typing import Callable, Optional, Sequence, cast

from examples.sidelay.output.overlay_window import CellValue, OverlayRow, OverlayWindow
from examples.sidelay.output.utils import COLUMN_NAMES, STAT_LEVELS, rate_value
from examples.sidelay.state import OverlayState
from examples.sidelay.stats import PropertyName, Stats

DEFAULT_COLOR = "snow"
LEVEL_COLORMAP = (
    "gray60",
    "snow",
    "yellow",
    "orange red",
    "red",
)

for levels in STAT_LEVELS.values():
    if levels is not None:
        assert len(levels) <= len(LEVEL_COLORMAP) - 1

COLUMN_ORDER: Sequence[PropertyName] = cast(
    Sequence[PropertyName], ("username", "stars", "fkdr", "winstreak")
)


def stats_to_row(stats: Stats) -> OverlayRow[PropertyName]:
    """
    Create an OverlayRow from a Stats instance

    Gets the text from stats.get_string
    Gets the color by rating the stats
    """
    return {
        name: CellValue(
            text=stats.get_string(name),
            color=(
                LEVEL_COLORMAP[rate_value(value, levels)]
                if levels is not None
                and isinstance(value := stats.get_value(name), (int, float))
                else DEFAULT_COLOR
            ),
        )
        for name, levels in STAT_LEVELS.items()
    }


def run_overlay(
    state: OverlayState, fetch_state_updates: Callable[[], Optional[list[Stats]]]
) -> None:
    """
    Run the overlay

    The parameter fetch_state_updates should check for new state updates and
    return a list of stats if the state changed.
    """

    def get_new_data() -> tuple[
        bool, Optional[CellValue], Optional[list[OverlayRow[PropertyName]]]
    ]:
        new_stats = fetch_state_updates()
        new_rows = (
            [stats_to_row(stats) for stats in new_stats]
            if new_stats is not None
            else None
        )
        return (
            state.in_queue,
            CellValue("Overlay out of sync. Use /who", "red")
            if state.out_of_sync
            else None,
            new_rows,
        )

    def set_not_in_queue() -> None:
        state.in_queue = False

    overlay = OverlayWindow[PropertyName](
        column_order=COLUMN_ORDER,
        column_names=COLUMN_NAMES,
        left_justified_columns={0},
        close_callback=lambda: sys.exit(0),
        minimize_callback=set_not_in_queue,
        get_new_data=get_new_data,
        poll_interval=100,
        start_hidden=True,
    )
    overlay.run()
