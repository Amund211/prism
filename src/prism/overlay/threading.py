import logging
import os
import queue
import sys
import threading
import time
from collections.abc import Callable, Iterable
from functools import cache

from prism.overlay.behaviour import get_stats_and_winstreak, should_redraw
from prism.overlay.controller import OverlayController
from prism.overlay.player import Player, sort_players
from prism.overlay.process_event import process_loglines
from prism.overlay.rich_presence import RPCThread
from prism.update_checker import update_available

logger = logging.getLogger(__name__)


def get_cpu_count() -> int | None:
    """Return the amount of logical cores on the computer, None if failure"""
    try:
        return os.cpu_count()
    except OSError:  # pragma: no coverage
        logger.exception("Failed getting cpu count")
        return None


def recommend_stats_thread_count_from_cpu_count(cpu_count: int | None) -> int:
    """Recommend cpu_count restricted to [2, 16], 2 if failure"""
    if cpu_count is not None:
        # Restrict number of threads to [2, 16]
        return max(2, min(16, cpu_count))

    logger.warning("Failed getting cpu count, defaulting to 2 stats threads")
    return 2


@cache
def recommend_stats_thread_count() -> int:
    """Recommend an amount of concurrent stats thread for the current cpu"""
    return recommend_stats_thread_count_from_cpu_count(get_cpu_count())


class UpdateStateThread(threading.Thread):  # pragma: nocover
    """Thread that reads from the logfile and updates the state"""

    def __init__(self, controller: OverlayController, loglines: Iterable[str]) -> None:
        super().__init__(daemon=True)  # Don't block the process from exiting
        self.controller = controller
        self.loglines = loglines

    def run(self) -> None:
        """Read self.loglines and update self.controller"""
        try:
            process_loglines(self.loglines, self.controller)
        except Exception:
            logger.exception(
                "Exception caught in state update thread. Exiting the overlay."
            )
            # Without state updates the overlay will stop working -> force quit
            sys.exit(1)


class GetStatsThread(threading.Thread):  # pragma: nocover
    """Thread that downloads and stores players' stats to cache"""

    def __init__(
        self,
        requests_queue: queue.Queue[str],
        completed_queue: queue.Queue[str],
        controller: OverlayController,
    ) -> None:
        super().__init__(daemon=True)  # Don't block the process from exiting
        self.requests_queue = requests_queue
        self.completed_queue = completed_queue
        self.controller = controller

    def run(self) -> None:
        """Get requested stats from the queue and download them"""
        try:
            while True:
                username = self.requests_queue.get()

                # Small optimization in case the player left or we switched lobbies
                # between first seeing them and now getting to the request
                # NOTE: We always allow own_username to enable the discord RPC thread
                #       to make requests to compute session stats
                state = self.controller.state
                if username in state.lobby_players or username == state.own_username:
                    get_stats_and_winstreak(
                        username=username,
                        completed_queue=self.completed_queue,
                        controller=self.controller,
                    )
                else:
                    logger.info(f"Skipping get_stats for {username} because they left")
                    # Uncache the pending stats so that if we see them again we will
                    # issue another request, instead of waiting for this one.
                    self.controller.player_cache.uncache_player(username)

                self.requests_queue.task_done()
        except Exception:
            logger.exception("Exception caught in stats thread. Exiting.")
            # Since we spawn multiple stats threads at the start, we can afford some
            # casualties without the overlay completely breaking


class UpdateCheckerThread(threading.Thread):  # pragma: nocover
    """Thread that checks for updates on GitHub once a day"""

    PERIOD_SECONDS = 24 * 60 * 60

    def __init__(
        self,
        one_shot: bool,
        update_available_event: threading.Event,
        controller: OverlayController,
    ) -> None:
        super().__init__(daemon=True)  # Don't block the process from exiting
        self.one_shot = one_shot
        self.update_available_event = update_available_event
        self.controller = controller

    def run(self) -> None:
        """Run update_available and set the event accordingly"""
        try:
            while True:
                logger.info("UpdateChecker: checking for updates.")
                if not self.controller.settings.check_for_updates:
                    logger.info("UpdateChecker: disabled by settings.")
                elif update_available(
                    ignore_patch_bumps=(
                        not self.controller.settings.include_patch_updates
                    )
                ):
                    logger.info("UpdateChecker: update available!")
                    self.update_available_event.set()
                    # An update is available -> no need to check any more
                    return
                else:
                    logger.info("UpdateChecker: no update available.")

                if self.one_shot:
                    logger.info("UpdateChecker: exiting oneshot thread.")
                    return

                time.sleep(self.PERIOD_SECONDS)
        except Exception:
            logger.exception("Exception caught in update checker thread. Exiting.")


def prepare_overlay(
    controller: OverlayController, loglines: Iterable[str]
) -> Callable[[], list[Player] | None]:  # pragma: nocover
    """
    Set up and return get_stat_list

    get_stat_list returns an updated list of stats of the players in the lobby,
    or None if no updates happened since last call.

    This function spawns threads that perform the state updates and stats downloading
    """

    # Usernames we want the stats of
    requested_stats_queue = queue.Queue[str]()
    # Usernames we have newly downloaded the stats of
    completed_stats_queue = queue.Queue[str]()

    # Spawn thread for updating state
    UpdateStateThread(controller=controller, loglines=loglines).start()

    # Spawn threads for downloading stats
    for i in range(controller.settings.stats_thread_count):
        GetStatsThread(
            requests_queue=requested_stats_queue,
            completed_queue=completed_stats_queue,
            controller=controller,
        ).start()

    RPCThread(
        controller=controller, requested_stats_queue=requested_stats_queue
    ).start()

    def get_stat_list() -> list[Player] | None:
        """
        Get an updated list of stats of the players in the lobby. None if no updates
        """

        redraw = should_redraw(controller, completed_stats_queue=completed_stats_queue)

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
                requested_stats_queue.put(player)
            players.append(cached_stats)

        sorted_stats = sort_players(
            players,
            state.party_members,
            controller.settings.sort_order,
            sort_ascending=False,
        )

        return sorted_stats

    return get_stat_list
