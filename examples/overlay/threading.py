import functools
import logging
import queue
import threading
from collections.abc import Callable, Iterable

from examples.overlay.controller import OverlayController
from examples.overlay.get_stats import get_bedwars_stats
from examples.overlay.parsing import parse_logline
from examples.overlay.player import (
    MISSING_WINSTREAKS,
    KnownPlayer,
    Player,
    sort_players,
)
from examples.overlay.process_event import process_event

logger = logging.getLogger(__name__)


class UpdateStateThread(threading.Thread):
    """Thread that reads from the logfile and updates the state"""

    def __init__(
        self,
        controller: OverlayController,
        loglines: Iterable[str],
        redraw_event: threading.Event,
    ) -> None:
        super().__init__(daemon=True)  # Don't block the process from exiting
        self.controller = controller
        self.loglines = loglines
        self.redraw_event = redraw_event

    def run(self) -> None:
        """Read self.loglines and update self.controller"""
        try:
            for line in self.loglines:
                event = parse_logline(line)

                if event is None:
                    continue

                with self.controller.state.mutex:
                    redraw = process_event(self.controller, event)

                if redraw:
                    # Tell the main thread we need a redraw
                    self.redraw_event.set()
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

                # get_bedwars_stats sets the stats cache which will be read from later
                player = get_bedwars_stats(username, self.controller)

                # Tell the main thread that we downloaded this user's stats
                self.completed_queue.put(username)

                logger.debug(f"Finished gettings stats for {username}")

                if isinstance(player, KnownPlayer) and player.is_missing_winstreaks:
                    (
                        estimated_winstreaks,
                        winstreaks_accurate,
                    ) = self.controller.get_estimated_winstreaks(player.uuid)

                    if estimated_winstreaks is MISSING_WINSTREAKS:
                        logger.debug(
                            f"Updating missing winstreak for {username} failed"
                        )
                    else:
                        for alias in player.aliases:
                            self.controller.player_cache.update_cached_player(
                                alias,
                                functools.partial(
                                    KnownPlayer.update_winstreaks,
                                    **estimated_winstreaks,
                                    winstreaks_accurate=winstreaks_accurate,
                                ),
                            )

                        # Tell the main thread that we got the estimated winstreak
                        self.completed_queue.put(username)
                        logger.debug(f"Updated missing winstreak for {username}")

                self.requests_queue.task_done()
        except Exception as e:
            logger.exception(f"Exception caught in stats thread: {e}. Exiting")
            return


def should_redraw(
    controller: OverlayController,
    redraw_event: threading.Event,
    completed_stats_queue: queue.Queue[str],
) -> bool:
    """Check if any updates happened since last time that needs a redraw"""
    # Check if the state update thread has issued any redraws since last time
    redraw = redraw_event.is_set()

    # Check if any of the stats downloaded since last render are still in the lobby
    while True:
        try:
            username = completed_stats_queue.get_nowait()
        except queue.Empty:
            break
        else:
            completed_stats_queue.task_done()
            if not redraw:
                with controller.state.mutex:
                    if username in controller.state.lobby_players:
                        # We just received the stats of a player in the lobby
                        # Redraw the screen in case the stats weren't there last time
                        redraw = True

    if redraw:
        # We are going to redraw - clear any redraw request
        redraw_event.clear()

    return redraw


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
    # Redraw requests from state updates
    redraw_event = threading.Event()

    # Spawn thread for updating state
    UpdateStateThread(
        controller=controller, loglines=loglines, redraw_event=redraw_event
    ).start()

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

        redraw = should_redraw(
            controller,
            redraw_event=redraw_event,
            completed_stats_queue=completed_stats_queue,
        )

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
