"""Thread for keeping track of the stats of the current player"""

import logging
import threading
from dataclasses import dataclass
from typing import Callable

from prism.overlay.behaviour import get_cached_player_or_enqueue_request
from prism.overlay.controller import OverlayController
from prism.player import KnownPlayer

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class UsernameUpdate:
    username: str | None
    name_changed: bool = False
    game_ended: bool = False


class CurrentPlayerThread(threading.Thread):
    """Thread for keeping track of the stats of the current player"""

    def __init__(
        self,
        controller: OverlayController,
        sleep: Callable[[float], None],
        timeout: float = 15,
    ) -> None:
        super().__init__(daemon=True)  # Don't block the process from exiting
        self.controller = controller
        self.sleep = sleep
        self.timeout = timeout

        self.username: str | None = None
        self.previous_player: KnownPlayer | None = None

    def run(self) -> None:  # pragma: no coverage
        while True:
            self.process_updates()

    def process_updates(self) -> None:
        """
        Run a single step of the state machine for updating the current player stats
        """
        result = self.get_username_updates()

        self.username = result.username

        if self.username is None:
            return

        if result.name_changed:
            self.previous_player = None
            self.controller.game_ended_event.clear()
            player = self.get_player(self.username)
            if player is None:
                return

            # Let consumers know about the latest player stats
            self.controller.current_player_updates_queue.put(player)

            self.previous_player = player

        if result.game_ended:
            self.sleep(5)  # Wait a bit to let Hypixel update the stats in the API

            self.controller.game_ended_event.clear()
            player = self.get_player(self.username)
            if player is None:
                return

            # Let consumers know about the latest player stats
            self.controller.current_player_updates_queue.put(player)

            old_player = self.previous_player
            self.previous_player = player

            if old_player is None:
                return

            # If the player did not get another game registered, the stats are probably
            # a stale cache hit. Wait a minute and try again.
            # TODO: This should use games played and not wins, as we might get here
            #       after a loss.
            if old_player.stats.wins == player.stats.wins:
                logger.info("Stats did not change after game end, waiting to retry")
                self.sleep(65)

                player = self.get_player(self.username)
                if player is None:
                    return

                # Let consumers know about the latest player stats
                self.controller.current_player_updates_queue.put(player)

                self.previous_player = player

    def get_username_updates(
        self,
    ) -> UsernameUpdate:
        """Return the current username and whether we should update their stats"""
        new_username = self.controller.state.own_username

        if new_username != self.username:
            if new_username is not None:
                # New username
                return UsernameUpdate(new_username, name_changed=True)
            else:
                # No username
                return UsernameUpdate(None, name_changed=True)

        if self.username is None:
            # Still no username
            return UsernameUpdate(None)

        if self.controller.game_ended_event.wait(timeout=self.timeout):
            # Game ended, update stats
            return UsernameUpdate(self.username, game_ended=True)

        return UsernameUpdate(self.username)

    def get_player(self, username: str) -> KnownPlayer | None:
        """Request and wait for the stats of the player"""
        # Wait for the stats to become available
        for _ in range(60):  # Up to 60 seconds
            player = get_cached_player_or_enqueue_request(self.controller, username)

            if isinstance(player, KnownPlayer):
                return player

            self.sleep(1)

        return None  # Timed out getting player data
