import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from typing import Self

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OverlayState:
    """
    Dataclass holding the state of the overlay

    NOTE: Don't store any mutable data, as shallow copies are performed on this class.
    """

    party_members: frozenset[str] = frozenset()
    lobby_players: frozenset[str] = frozenset()
    alive_players: frozenset[str] = frozenset()
    last_game_start: float | None = None
    out_of_sync: bool = False
    in_queue: bool = False
    own_username: str | None = None
    now_func: Callable[[], float] = field(default=time.monotonic, compare=False)

    def join_queue(self) -> Self:
        """
        Join a queue by setting in_queue = True

        NOTE: Can modify the lobby, so call this before making any changes
        """
        if self.in_queue:
            return self

        if self.lobby_players != self.alive_players:
            # This is a new queue and we have dirty state from a previous game
            # Clear the lobby
            logger.info("Joining a new queue and clearing the lobby due to dirty state")
            new_state = self.clear_lobby()
        else:
            # This is a new queue, but lobby_players and alive_players are in sync
            # This is likely due to the user typing /who before anyone could join
            logger.info(
                f"Joining a new queue with lobby_players and alive_players in sync. "
                f"Setting in_queue, but keeping the current lobby {self.lobby_players=}"
            )
            new_state = self

        return replace(new_state, in_queue=True)

    def leave_queue(self) -> Self:
        """
        Leave a queue by setting in_queue = False

        NOTE: The game starting counts as leaving the queue.
        """
        logger.info("Leaving the queue")
        return replace(self, in_queue=False)

    def join_game(self) -> Self:
        """Join a bedwars game"""
        logger.info("Joining game")
        return replace(self, last_game_start=self.now_func())

    def leave_game(self) -> Self:
        """Leave a bedwars game"""
        logger.info("Leaving game")
        return replace(self, last_game_start=None)

    @property
    def in_game(self) -> float | None:
        """Return True if the player is currently in a game"""
        return self.last_game_start is not None

    @property
    def time_in_game(self) -> float | None:
        """Time in seconds since the last game started"""
        if self.last_game_start is None:
            return None
        return self.now_func() - self.last_game_start

    def add_to_party(self, username: str) -> Self:
        """Add the given username to the party"""
        return replace(self, party_members=self.party_members | {username})

    def remove_from_party(self, username: str) -> Self:
        """Remove the given username from the party"""
        if username not in self.party_members:
            logger.warning(
                f"Tried removing {username} from the party, but they were not in it!"
            )
            return self

        return replace(self, party_members=self.party_members - {username})

    def clear_party(self) -> Self:
        """Remove all players from the party, except for yourself"""
        logger.info("Clearing the party")

        new_party: frozenset[str]
        if self.own_username is None:
            logger.warning("Own username is not set, party is now empty")
            new_party = frozenset()
        else:
            new_party = frozenset({self.own_username})

        return replace(self, party_members=new_party)

    def add_to_lobby(self, username: str) -> Self:
        """Add the given username to the lobby"""
        return replace(
            self,
            lobby_players=self.lobby_players | {username},
            alive_players=self.alive_players | {username},
        )

    def set_lobby(self, new_lobby: Iterable[str]) -> Self:
        """Set the lobby to be the given lobby"""
        new_lobby_set = frozenset(new_lobby)
        return replace(self, lobby_players=new_lobby_set, alive_players=new_lobby_set)

    def clear_lobby(self) -> Self:
        """Remove all players from the lobby"""
        # Don't include yourself in the new lobby.
        # Your name usually appears as a join message anyway, and you may be nicked
        return self.set_lobby([])

    def mark_dead(self, username: str) -> Self:
        """Mark the given username as dead"""
        if username not in self.alive_players:
            # If the player was missing from lobby_players (due to missing /who)
            # we now know that they are, in fact, in the lobby, so simply add them
            return replace(self, lobby_players=self.lobby_players | {username})

        return replace(self, alive_players=self.alive_players - {username})

    def mark_alive(self, username: str) -> Self:
        """Mark the given username as alive"""

        if username in self.alive_players:
            logger.warning(
                f"Tried marking {username} as alive, but they were already alive!"
            )
            new_state = self
        else:
            new_state = replace(self, alive_players=self.alive_players | {username})

        if username not in self.lobby_players:
            logger.warning(
                f"Marked {username} as alive, but they were not in the lobby! "
                "Adding them to the lobby."
            )
            new_state = replace(
                new_state, lobby_players=self.lobby_players | {username}
            )

        return new_state

    def set_out_of_sync(self, out_of_sync: bool) -> Self:
        """Set out_of_sync"""
        if self.out_of_sync != out_of_sync:
            return replace(self, out_of_sync=out_of_sync)

        return self
