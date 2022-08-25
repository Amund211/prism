import logging
import threading
from collections.abc import Callable

from cachetools import TTLCache

from examples.overlay.player import KnownPlayer, NickedPlayer, PendingPlayer, Player

logger = logging.getLogger(__name__)


class PlayerCache:
    def __init__(self) -> None:
        # Entries cached for 2mins, so they hopefully expire before the next queue
        self._cache: TTLCache[str, Player] = TTLCache(maxsize=512, ttl=120)
        self._mutex = threading.Lock()

    def set_player_pending(self, username: str) -> PendingPlayer:
        """Note that this user is pending"""
        pending_player = PendingPlayer(username)

        with self._mutex:
            if username in self._cache:
                logger.error(f"Player {username} set to pending, but already exists")

            self._cache[username] = pending_player

        return pending_player

    def set_cached_player(
        self, username: str, player: KnownPlayer | NickedPlayer
    ) -> None:
        with self._mutex:
            self._cache[username] = player

    def get_cached_player(self, username: str) -> Player | None:
        with self._mutex:
            return self._cache.get(username, None)

    def update_cached_player(
        self, username: str, update: Callable[[KnownPlayer], KnownPlayer]
    ) -> None:
        """Update the cache for a player"""
        with self._mutex:
            player = self._cache.get(username, None)
            if isinstance(player, KnownPlayer):
                self._cache[username] = update(player)
            else:
                logger.warning(f"Player {username} not found during update")

    def uncache_player(self, username: str) -> None:
        """Clear the cache entry for `username`"""
        with self._mutex:
            self._cache.pop(username, None)

    def clear_cache(self) -> None:
        """Clear the entire player cache"""
        with self._mutex:
            self._cache.clear()
