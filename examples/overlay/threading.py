import logging
import queue
import threading
from collections.abc import Callable, Iterable

from examples.overlay.behaviour import (
    get_stats_and_winstreak,
    process_loglines,
    should_redraw,
)
from examples.overlay.controller import OverlayController
from examples.overlay.player import Player, sort_players

logger = logging.getLogger(__name__)


class UpdateStateThread(threading.Thread):
    """Thread that reads from the logfile and updates the state"""

    def __init__(self, controller: OverlayController, loglines: Iterable[str]) -> None:
        super().__init__(daemon=True)  # Don't block the process from exiting
        self.controller = controller
        self.loglines = loglines

    def run(self) -> None:
        """Read self.loglines and update self.controller"""
        try:
            process_loglines(self.loglines, self.controller)
        except Exception as e:
            logger.exception(f"Exception caught in state update thread: {e}. Exiting")
            return


class GetStatsThread(threading.Thread):
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

                get_stats_and_winstreak(
                    username=username,
                    completed_queue=self.completed_queue,
                    controller=self.controller,
                )

                self.requests_queue.task_done()
        except Exception as e:
            logger.exception(f"Exception caught in stats thread: {e}. Exiting")
            return


def prepare_overlay(
    controller: OverlayController, loglines: Iterable[str], thread_count: int
) -> Callable[[], list[Player] | None]:
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
    for i in range(thread_count):
        GetStatsThread(
            requests_queue=requested_stats_queue,
            completed_queue=completed_stats_queue,
            controller=controller,
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

        with controller.state.mutex:
            lobby_players = controller.state.lobby_players.copy()
            party_members = controller.state.party_members.copy()

        for player in lobby_players:
            cached_stats = controller.player_cache.get_cached_player(player)
            if cached_stats is None:
                # No query made for this player yet
                # Start a query and note that a query has been started
                cached_stats = controller.player_cache.set_player_pending(player)
                logger.debug(f"Set player {player} to pending")
                requested_stats_queue.put(player)
            players.append(cached_stats)

        sorted_stats = sort_players(players, party_members)

        return sorted_stats

    return get_stat_list
