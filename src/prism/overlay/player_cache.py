import logging
import threading
from collections.abc import Callable

from cachetools import TTLCache

from prism.overlay.player import KnownPlayer, NickedPlayer, PendingPlayer, Player

logger = logging.getLogger(__name__)


class PlayerCache:
    def __init__(self) -> None:
        # Cache genus. Cached entries from old genera are discarded.
        self.current_genus = 0

        # Entries cached for 2mins, so they hopefully expire before the next queue
        self._cache = TTLCache[str, Player](maxsize=512, ttl=120)

        # Optional long term cache accessed with kwarg long_term=True
        # Can be used to prevent refetching during a game (while stats don't change)
        self._long_term_cache = TTLCache[str, Player](maxsize=512, ttl=60 * 60)

        # TTLCache is not thread-safe so we use a mutex to synchronize threads
        self._mutex = threading.Lock()

    def set_player_pending(self, username: str) -> PendingPlayer:
        """Note that this user is pending"""
        pending_player = PendingPlayer(username)

        with self._mutex:
            if username in self._cache:
                logger.error(f"Player {username} set to pending, but already exists")

            self._cache[username] = self._long_term_cache[username] = pending_player

        return pending_player

    def set_cached_player(
        self, username: str, player: KnownPlayer | NickedPlayer, genus: int
    ) -> None:
        with self._mutex:
            if genus != self.current_genus:
                logger.warning(
                    f"Tried to store stats for {username} with old genus. Ignoring. "
                    f"{genus=}!={self.current_genus=}, {player=}"
                )
                return

            self._cache[username] = self._long_term_cache[username] = player

    def get_cached_player(
        self, username: str, *, long_term: bool = False
    ) -> Player | None:
        with self._mutex:
            return (
                self._cache.get(username, None)
                if not long_term
                else self._long_term_cache.get(username, None)
            )

    def update_cached_player(
        self, username: str, update: Callable[[KnownPlayer], KnownPlayer]
    ) -> None:
        """Update the cache for a player"""
        with self._mutex:
            player = self._cache.get(username, None)
            if isinstance(player, KnownPlayer):
                self._cache[username] = self._long_term_cache[username] = update(player)
            else:
                logger.warning(f"Player {username} not found during update")

    def uncache_player(self, username: str) -> None:
        """Clear the cache entry for `username`"""
        with self._mutex:
            self._cache.pop(username, None)
            self._long_term_cache.pop(username, None)

    def clear_cache(self, *, short_term_only: bool = False) -> None:
        """Clear the entire player cache"""
        with self._mutex:
            self.current_genus += 1
            self._cache.clear()
            if not short_term_only:
                self._long_term_cache.clear()
