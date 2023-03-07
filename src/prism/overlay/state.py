import logging
from collections.abc import Iterable
from dataclasses import dataclass, replace

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
    out_of_sync: bool = False
    in_queue: bool = False
    own_username: str | None = None

    def join_queue(self) -> "OverlayState":
        """
        Join a queue by setting in_queue = True

        NOTE: Can modify the lobby, so call this before making any changes
        """
        if not self.in_queue:
            # This is a new queue -> clear the last lobby
            logger.info("Joining a new queue and clearing lobby")
            return replace(self.clear_lobby(), in_queue=True)

        return self

    def leave_queue(self) -> "OverlayState":
        """
        Leave a queue by setting in_queue = False

        NOTE: The game starting counts as leaving the queue.
        """
        logger.info("Leaving the queue")
        return replace(self, in_queue=False)

    def add_to_party(self, username: str) -> "OverlayState":
        """Add the given username to the party"""
        return replace(self, party_members=self.party_members | {username})

    def remove_from_party(self, username: str) -> "OverlayState":
        """Remove the given username from the party"""
        if username not in self.party_members:
            logger.warning(
                f"Tried removing {username} from the party, but they were not in it!"
            )
            return self

        return replace(self, party_members=self.party_members - {username})

    def clear_party(self) -> "OverlayState":
        """Remove all players from the party, except for yourself"""
        logger.info("Clearing the party")

        new_party: frozenset[str]
        if self.own_username is None:
            logger.warning("Own username is not set, party is now empty")
            new_party = frozenset()
        else:
            new_party = frozenset({self.own_username})

        return replace(self, party_members=new_party)

    def add_to_lobby(self, username: str) -> "OverlayState":
        """Add the given username to the lobby"""
        return replace(
            self,
            lobby_players=self.lobby_players | {username},
            alive_players=self.alive_players | {username},
        )

    def remove_from_lobby(self, username: str) -> "OverlayState":
        """Remove the given username from the lobby"""
        if username not in self.lobby_players:
            new_lobby = self.lobby_players
            logger.warning(
                f"Tried removing {username} from the lobby, but they were not in it!"
            )
        else:
            new_lobby = self.lobby_players - {username}

        if username not in self.alive_players:
            new_alive = self.alive_players
            logger.warning(
                f"Tried removing {username} from the lobby, but they were not alive!"
            )
        else:
            new_alive = self.alive_players - {username}

        return replace(self, lobby_players=new_lobby, alive_players=new_alive)

    def set_lobby(self, new_lobby: Iterable[str]) -> "OverlayState":
        """Set the lobby to be the given lobby"""
        new_lobby_set = frozenset(new_lobby)
        return replace(self, lobby_players=new_lobby_set, alive_players=new_lobby_set)

    def clear_lobby(self) -> "OverlayState":
        """Remove all players from the lobby"""
        # Don't include yourself in the new lobby.
        # Your name usually appears as a join message anyway, and you may be nicked
        return self.set_lobby([])

    def mark_dead(self, username: str) -> "OverlayState":
        """Mark the given username as dead"""
        if username not in self.alive_players:
            logger.warning(
                f"Tried marking {username} as dead, but they were not alive!"
            )
            return self

        return replace(self, alive_players=self.alive_players - {username})

    def mark_alive(self, username: str) -> "OverlayState":
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

    def set_out_of_sync(self, out_of_sync: bool) -> "OverlayState":
        """Set out_of_sync"""
        if self.out_of_sync != out_of_sync:
            return replace(self, out_of_sync=out_of_sync)

        return self
