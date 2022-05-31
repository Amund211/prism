import functools
import logging
import queue
import threading
from typing import Callable, Iterable, Optional

import examples.overlay.antisniper_api as antisniper_api
from examples.overlay.parsing import parse_logline
from examples.overlay.state import OverlayState, update_state
from examples.overlay.stats import (
    KnownPlayer,
    Player,
    get_bedwars_stats,
    get_cached_stats,
    set_player_pending,
    sort_players,
    update_cached_stats,
    update_winstreak,
)
from prism.playerdata import HypixelAPIKeyHolder

logger = logging.getLogger(__name__)


class UpdateStateThread(threading.Thread):
    """Thread that reads from the logfile and updates the state"""

    def __init__(
        self,
        state: OverlayState,
        loglines: Iterable[str],
        redraw_event: threading.Event,
    ) -> None:
        super().__init__(daemon=True)  # Don't block the process from exiting
        self.state = state
        self.loglines = loglines
        self.redraw_event = redraw_event

    def run(self) -> None:
        """Read self.loglines and update self.state"""
        try:
            for line in self.loglines:
                event = parse_logline(line)

                if event is None:
                    continue

                with self.state.mutex:
                    redraw = update_state(self.state, event)

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
        hypixel_key_holder: HypixelAPIKeyHolder,
        antisniper_key_holder: antisniper_api.AntiSniperAPIKeyHolder | None,
        denick: Callable[[str], Optional[str]],
    ) -> None:
        super().__init__(daemon=True)  # Don't block the process from exiting
        self.requests_queue = requests_queue
        self.completed_queue = completed_queue
        self.hypixel_key_holder = hypixel_key_holder
        self.antisniper_key_holder = antisniper_key_holder
        self.denick = denick

    def run(self) -> None:
        """Get requested stats from the queue and download them"""
        try:
            while True:
                username = self.requests_queue.get()

                # get_bedwars_stats sets the stats cache which will be read from later
                found_username, nick, uuid, player = get_bedwars_stats(
                    username, key_holder=self.hypixel_key_holder, denick=self.denick
                )
                logger.debug(f"Finished gettings stats for {username}")
                self.requests_queue.task_done()

                # Tell the main thread that we downloaded this user's stats
                self.completed_queue.put(username)

                if (
                    self.antisniper_key_holder is not None
                    and uuid is not None
                    and isinstance(player, KnownPlayer)
                    and player.stats.winstreak is None
                ):
                    (
                        estimated_winstreak,
                        winstreak_accurate,
                    ) = antisniper_api.get_estimated_winstreak(
                        uuid=uuid, key_holder=self.antisniper_key_holder
                    )

                    if estimated_winstreak is not None:
                        for key in (found_username, nick):
                            if key is None:
                                continue

                            update_cached_stats(
                                username,
                                functools.partial(
                                    update_winstreak,
                                    winstreak=estimated_winstreak,
                                    winstreak_accurate=winstreak_accurate,
                                ),
                            )

                            # Tell the main thread that we got the estimated winstreak
                            self.completed_queue.put(key)

        except Exception as e:
            logger.exception(f"Exception caught in stats thread: {e}. Exiting")
            return


def should_redraw(
    state: OverlayState,
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
                with state.mutex:
                    if username in state.lobby_players:
                        # We just received the stats of a player in the lobby
                        # Redraw the screen in case the stats weren't there last time
                        redraw = True

    if redraw:
        # We are going to redraw - clear any redraw request
        redraw_event.clear()

    return redraw


def prepare_overlay(
    state: OverlayState,
    hypixel_key_holder: HypixelAPIKeyHolder,
    antisniper_key_holder: antisniper_api.AntiSniperAPIKeyHolder | None,
    denick: Callable[[str], Optional[str]],
    loglines: Iterable[str],
    thread_count: int,
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
    UpdateStateThread(state=state, loglines=loglines, redraw_event=redraw_event).start()

    # Spawn threads for downloading stats
    for i in range(thread_count):
        GetStatsThread(
            requests_queue=requested_stats_queue,
            completed_queue=completed_stats_queue,
            hypixel_key_holder=hypixel_key_holder,
            antisniper_key_holder=antisniper_key_holder,
            denick=denick,
        ).start()

    def get_stat_list() -> list[Player] | None:
        """
        Get an updated list of stats of the players in the lobby. None if no updates
        """

        redraw = should_redraw(
            state,
            redraw_event=redraw_event,
            completed_stats_queue=completed_stats_queue,
        )

        if not redraw:
            return None

        # Get the cached stats for the players in the lobby
        players: list[Player] = []

        with state.mutex:
            lobby_players = state.lobby_players.copy()

        for player in lobby_players:
            cached_stats = get_cached_stats(player)
            if cached_stats is None:
                # No query made for this player yet
                # Start a query and note that a query has been started
                cached_stats = set_player_pending(player)
                logger.debug(f"Set player {player} to pending")
                requested_stats_queue.put(player)
            players.append(cached_stats)

        sorted_stats = sort_players(players, state.party_members)

        return sorted_stats

    return get_stat_list
