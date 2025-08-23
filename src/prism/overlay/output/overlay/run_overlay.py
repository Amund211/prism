import math
import threading
import time
from collections.abc import Callable

from prism.overlay.controller import OverlayController
from prism.overlay.output.cells import InfoCellValue
from prism.overlay.output.overlay.stats_overlay import StatsOverlay
from prism.overlay.output.overlay.utils import OverlayRowData, player_to_row
from prism.overlay.threading import UpdateCheckerThread
from prism.player import Player


def run_overlay(
    controller: OverlayController,
    fetch_state_updates: Callable[[], list[Player] | None],
) -> None:  # pragma: nocover
    """
    Run the overlay

    The parameter fetch_state_updates should check for new state updates and
    return a list of stats if the state changed.
    """

    # Spawn thread to check for updates on GitHub
    update_available_event = threading.Event()
    UpdateCheckerThread(
        one_shot=False,
        update_available_event=update_available_event,
        controller=controller,
    ).start()

    def get_new_data() -> tuple[bool, list[InfoCellValue], list[OverlayRowData] | None]:
        # Store a persistent view to the current state
        state = controller.state

        new_players = fetch_state_updates()
        new_rows = (
            [
                player_to_row(player, controller.settings.rating_configs)
                for player in new_players
            ]
            if new_players is not None
            else None
        )

        info_cells = []
        if state.out_of_sync:
            info_cells.append(
                InfoCellValue(
                    text="Overlay out of sync. Use /who", color="orange", url=None
                )
            )

        if controller.api_key_invalid:
            info_cells.append(
                InfoCellValue(
                    text="Invalid API key. Get a new one from antisniper.net",
                    color="red" if time.monotonic() % 2 > 1 else "white",
                    url=None,
                )
            )

        antisniper_block_duration_seconds = (
            controller.antisniper_key_holder.limiter.block_duration_seconds
            if controller.antisniper_key_holder is not None
            else 0
        )
        block_duration_seconds = max(
            antisniper_block_duration_seconds,
            controller.api_limiter.block_duration_seconds,
        )

        if block_duration_seconds > 0:
            pause = math.ceil(block_duration_seconds)
            info_cells.append(
                InfoCellValue(
                    text=f"Too many requests. Slowing down. ({pause}s)",
                    color="yellow",
                    url=None,
                )
            )

        if controller.missing_local_issuer_certificate:
            info_cells.append(
                InfoCellValue(
                    text=(
                        "SSL certificate error.\n"
                        "Change the 'Use included ssl certificates' setting\n"
                        "in the settings menu and *RESTART* the overlay."
                    ),
                    color="red",
                    url=None,
                )
            )

        if controller.api_key_throttled:
            info_cells.append(
                InfoCellValue(
                    text="Hypixel ratelimit reached! Wait time ~1 min.",
                    color="orange" if time.monotonic() % 2 > 1 else "white",
                    url=None,
                )
            )

        if controller.settings.check_for_updates and update_available_event.is_set():
            info_cells.append(
                InfoCellValue(
                    text="New update available! Click here to download.",
                    color="light green",
                    url="https://github.com/Amund211/prism/releases/latest/",
                )
            )

        # Store a copy to avoid TOCTOU
        controller_wants_shown = controller.wants_shown
        if controller_wants_shown is not None:
            # The user has a preference -> honor it
            should_show = controller_wants_shown
        else:
            # Fall back to showing the overlay in queue and hiding it in game
            should_show = state.in_queue

        return should_show, info_cells, new_rows

    overlay = StatsOverlay(
        column_order=controller.settings.column_order,
        controller=controller,
        get_new_data=get_new_data,
        update_available_event=update_available_event,
        poll_interval=100,
        start_hidden=False,
    )
    overlay.run()
