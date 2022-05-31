import os
import sys
from typing import Callable, Optional

from examples.overlay.output.overlay_window import CellValue, OverlayRow, OverlayWindow
from examples.overlay.output.utils import (
    COLUMN_NAMES,
    COLUMN_ORDER,
    STAT_LEVELS,
    rate_value,
)
from examples.overlay.state import OverlayState
from examples.overlay.stats import Player, PropertyName

if os.name == "nt":
    from examples.overlay.platform.windows import toggle_fullscreen

    FULLSCREEN_CALLBACK: Optional[Callable[[], None]] = toggle_fullscreen
else:
    FULLSCREEN_CALLBACK = None


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


def player_to_row(player: Player) -> OverlayRow[PropertyName]:
    """
    Create an OverlayRow from a Player instance

    Gets the text from player.get_string
    Gets the color by rating the stats
    """
    return {
        name: CellValue(
            text=player.get_string(name),
            color=(
                LEVEL_COLORMAP[rate_value(value, levels)]
                if levels is not None
                and isinstance(value := player.get_value(name), (int, float))
                else DEFAULT_COLOR
            ),
        )
        for name, levels in STAT_LEVELS.items()
    }


def run_overlay(
    state: OverlayState, fetch_state_updates: Callable[[], list[Player] | None]
) -> None:
    """
    Run the overlay

    The parameter fetch_state_updates should check for new state updates and
    return a list of stats if the state changed.
    """

    def get_new_data() -> tuple[
        bool, Optional[CellValue], Optional[list[OverlayRow[PropertyName]]]
    ]:
        new_players = fetch_state_updates()
        new_rows = (
            [player_to_row(player) for player in new_players]
            if new_players is not None
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
        with state.mutex:
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
        fullscreen_callback=FULLSCREEN_CALLBACK,
    )
    overlay.run()
