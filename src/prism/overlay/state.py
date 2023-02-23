import logging
import threading
from collections.abc import Iterable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class OverlayState:
    """Dataclass holding the state of the overlay"""

    party_members: set[str]
    lobby_players: set[str]
    alive_players: set[str]
    out_of_sync: bool = False
    in_queue: bool = False
    own_username: str | None = None
    mutex: threading.Lock = field(
        default_factory=threading.Lock, init=False, compare=False, repr=False
    )

    def join_queue(self) -> None:
        """
        Join a queue by setting in_queue = True

        NOTE: Can modify the lobby, so call this before making any changes
        """
        if not self.in_queue:
            # This is a new queue -> clear the last lobby
            logger.info("Joining a new queue and clearing lobby")
            self.clear_lobby()

        self.in_queue = True

    def leave_queue(self) -> None:
        """
        Leave a queue by setting in_queue = False

        NOTE: The game starting counts as leaving the queue.
        """
        logger.info("Leaving the queue")
        self.in_queue = False

    def add_to_party(self, username: str) -> None:
        """Add the given username to the party"""
        self.party_members.add(username)

    def remove_from_party(self, username: str) -> None:
        """Remove the given username from the party"""
        if username not in self.party_members:
            logger.warning(
                f"Tried removing {username} from the party, but they were not in it!"
            )
            return

        self.party_members.remove(username)

    def clear_party(self) -> None:
        """Remove all players from the party, except for yourself"""
        logger.info("Clearing the party")
        self.party_members.clear()

        if self.own_username is None:
            logger.warning("Own username is not set, party is now empty")
        else:
            self.add_to_party(self.own_username)

    def add_to_lobby(self, username: str) -> None:
        """Add the given username to the lobby"""
        self.lobby_players.add(username)
        self.alive_players.add(username)

    def remove_from_lobby(self, username: str) -> None:
        """Remove the given username from the lobby"""
        if username not in self.lobby_players:
            logger.info(
                f"Tried removing {username} from the lobby, but they were not in it!"
            )
        else:
            self.lobby_players.remove(username)

        if username not in self.alive_players:
            logger.info(
                f"Tried removing {username} from the lobby, but they were not alive!"
            )
        else:
            self.alive_players.remove(username)

    def set_lobby(self, new_lobby: Iterable[str]) -> None:
        """Set the lobby to be the given lobby"""
        self.lobby_players = set(new_lobby)
        self.alive_players = self.lobby_players.copy()

    def clear_lobby(self) -> None:
        """Remove all players from the lobby"""
        # Don't include yourself in the new lobby.
        # Your name usually appears as a join message anyway, and you may be nicked
        self.set_lobby([])

    def mark_dead(self, username: str) -> None:
        """Mark the given username as dead"""
        if username not in self.alive_players:
            logger.info(f"Tried marking {username} as dead, but they were not alive!")
            return

        self.alive_players.remove(username)
