import logging
import math
import time
from collections.abc import Iterable

from prism.overlay.behaviour import should_redraw
from prism.overlay.controller import OverlayController
from prism.overlay.output.cells import InfoCellValue
from prism.overlay.output.overlay.stats_overlay import StatsOverlay
from prism.overlay.output.overlay.utils import OverlayRowData, player_to_row
from prism.overlay.rating import sort_players
from prism.overlay.threading import start_threads
from prism.player import KnownPlayer, Player

logger = logging.getLogger(__name__)


def get_stat_list(controller: OverlayController) -> list[Player] | None:
    """
    Get an updated list of stats of the players in the lobby. None if no updates
    """
    redraw = should_redraw(controller)

    if not redraw:
        return None

    # Get the cached stats for the players in the lobby
    players: list[Player] = []

    # Store a persistent view to the current state
    state = controller.state

    displayed_players = (
        state.alive_players
        if controller.settings.hide_dead_players
        else state.lobby_players
    )

    # Players who are present in the lobby twice - once nicked and once unnicked
    duplicate_nicked_usernames = []

    for player in displayed_players:
        # Use the short term cache in queue to refresh stats between games
        # When we are not in queue (in game) use the long term cache, as we don't
        # want to refetch all the stats when someone gets final killed
        cached_stats = controller.player_cache.get_cached_player(
            player, long_term=not state.in_queue
        )
        if cached_stats is None:
            # No query made for this player yet
            # Start a query and note that a query has been started
            cached_stats = controller.player_cache.set_player_pending(player)
            logger.debug(f"Set player {player} to pending")
            controller.requested_stats_queue.put(player)
        elif isinstance(cached_stats, KnownPlayer):
            if (
                cached_stats.nick is not None
                and cached_stats.username in displayed_players
            ):
                duplicate_nicked_usernames.append(cached_stats.username)

        players.append(cached_stats)

    def should_remove(player: Player) -> bool:
        """
        Return True if the player is a duplicate, and is the unnicked version.

        This version will have come from the party_members set.
        """
        if player.username not in duplicate_nicked_usernames:
            return False

        if isinstance(player, KnownPlayer):
            return player.nick is None

        return True

    # Filter out duplicate nicks
    players = [player for player in players if not should_remove(player)]

    sorted_stats = sort_players(
        players,
        state.party_members,
        controller.settings.sort_order,
        controller.settings.sort_ascending,
    )

    return sorted_stats


def run_overlay(
    controller: OverlayController,
    loglines: Iterable[str],
) -> None:  # pragma: nocover
    """Run the overlay"""
    start_threads(controller, loglines)

    def get_new_data() -> tuple[bool, list[InfoCellValue], list[OverlayRowData] | None]:
        # Store a persistent view to the current state
        state = controller.state

        new_players = get_stat_list(controller)
        new_rows = (
            [
                player_to_row(player, controller.settings.rating_configs)
                for player in new_players
            ]
            if new_players is not None
            else None
        )

        info_cells = []

        for notice in controller.flashlight_notices:
            if not notice.active:
                continue
            info_cells.append(
                InfoCellValue(
                    text=notice.message,
                    color=(
                        "light blue"
                        if notice.severity == "info"
                        else (
                            "orange"
                            if notice.severity == "warning"
                            else ("red" if time.monotonic() % 2 > 1 else "white")
                        )
                    ),
                    url=notice.url,
                )
            )

        if state.out_of_sync:
            info_cells.append(
                InfoCellValue(
                    text="Overlay out of sync. Use /who", color="orange", url=None
                )
            )

        if controller.urchin_api_key_invalid:
            info_cells.append(
                InfoCellValue(
                    text=(
                        "Invalid Urchin API key - using default\n"
                        "Update or remove the key in the settings menu."
                    ),
                    color="red" if time.monotonic() % 2 > 1 else "white",
                    url=None,
                )
            )

        block_duration_seconds = max(
            controller._winstreak_provider.seconds_until_unblocked,
            controller._player_provider.seconds_until_unblocked,
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

        if (
            controller.settings.check_for_updates
            and controller.update_available_event.is_set()
        ):
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
        poll_interval=100,
        start_hidden=False,
    )
    overlay.run()
