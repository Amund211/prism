import os
import sys
import time
from collections.abc import Callable

from examples.overlay.controller import OverlayController
from examples.overlay.output.overlay.stats_overlay import StatsOverlay
from examples.overlay.output.overlay.utils import CellValue, OverlayRow, player_to_row
from examples.overlay.output.utils import COLUMN_NAMES, COLUMN_ORDER
from examples.overlay.player import Player, PropertyName

if os.name == "nt":  # pragma: nocover
    from examples.overlay.platform.windows import toggle_fullscreen

    FULLSCREEN_CALLBACK: Callable[[], None] | None = toggle_fullscreen
else:  # pragma: nocover
    FULLSCREEN_CALLBACK = None


def run_overlay(
    controller: OverlayController,
    fetch_state_updates: Callable[[], list[Player] | None],
) -> None:  # pragma: nocover
    """
    Run the overlay

    The parameter fetch_state_updates should check for new state updates and
    return a list of stats if the state changed.
    """

    def get_new_data() -> tuple[
        bool, list[CellValue], list[OverlayRow[PropertyName]] | None
    ]:
        new_players = fetch_state_updates()
        new_rows = (
            [player_to_row(player) for player in new_players]
            if new_players is not None
            else None
        )

        info_cells = []
        if controller.state.out_of_sync:
            info_cells.append(CellValue("Overlay out of sync. Use /who", "orange"))

        if controller.api_key_invalid:
            info_cells.append(
                CellValue(
                    "Invalid API key. Use /api new",
                    "red" if time.time() % 2 > 1 else "white",
                )
            )

        return (
            controller.state.in_queue,
            info_cells,
            new_rows,
        )

    def set_not_in_queue() -> None:
        with controller.state.mutex:
            controller.state.in_queue = False

    overlay = StatsOverlay[PropertyName](
        column_order=COLUMN_ORDER,
        column_names=COLUMN_NAMES,
        left_justified_columns={0},
        controller=controller,
        close_callback=lambda: sys.exit(0),
        minimize_callback=set_not_in_queue,
        get_new_data=get_new_data,
        poll_interval=100,
        start_hidden=False,
        fullscreen_callback=FULLSCREEN_CALLBACK,
    )
    overlay.run()
