import logging
from dataclasses import dataclass
from typing import Iterable, Optional

logger = logging.getLogger()


@dataclass
class OverlayState:
    """Dataclass holding the state of the overlay"""

    party_members: set[str]  # NOTE: lower case
    lobby_players: set[str]
    out_of_sync: bool = False
    own_username: Optional[str] = None

    def add_to_party(self, username: str) -> None:
        """Add the given username to the party"""
        self.party_members.add(username.lower())

    def remove_from_party(self, username: str) -> None:
        """Remove the given username from the party"""
        if username.lower() not in self.party_members:
            logger.error(
                f"Tried removing {username} from the party, but they were not in it!"
            )
            return

        self.party_members.remove(username.lower())

    def clear_party(self) -> None:
        """Remove all players from the party, except for yourself"""
        self.party_members.clear()

        if self.own_username is None:
            logger.warning("Own username is not set, party is now empty")
        else:
            self.party_members.add(self.own_username.lower())

    def add_to_lobby(self, username: str) -> None:
        """Add the given username to the lobby"""
        self.lobby_players.add(username)

    def remove_from_lobby(self, username: str) -> None:
        """Remove the given username from the lobby"""
        if username not in self.lobby_players:
            logger.error(
                f"Tried removing {username} from the lobby, but they were not in it!"
            )
            return

        self.lobby_players.remove(username)

    def set_lobby(self, new_lobby: Iterable[str]) -> None:
        """Set the lobby to be the given lobby"""
        self.lobby_players = set(new_lobby)
