import logging
import threading
from collections.abc import Callable
from typing import Literal

from cachetools import TTLCache

from prism.player import KnownPlayer, NickedPlayer, PendingPlayer, Player, UnknownPlayer

logger = logging.getLogger(__name__)


class PlayerCache:
    def __init__(self) -> None:
        # Cache genus. Cached entries from old genera are discarded.
        self.current_genus = 0

        # Entries cached for 10mins, so they expire if they are not cleared by game end
        self._cache = TTLCache[str, Player](maxsize=512, ttl=10 * 60)

        # Optional long term cache accessed with kwarg long_term=True
        # Can be used to prevent refetching during a game (while stats don't change)
        self._long_term_cache = TTLCache[str, Player](maxsize=512, ttl=60 * 60)

        # TTLCache is not thread-safe so we use a mutex to synchronize threads
        self._mutex = threading.Lock()

    def get_cached_player_or_set_pending(
        self, username: str, *, long_term: bool = False
    ) -> tuple[Player, Literal[False]] | tuple[PendingPlayer, Literal[True]]:
        """
        Get the cached player, or set them to pending if not cached

        Returns a tuple of (player, was_set_pending)
        """
        cache_key = username.lower()

        with self._mutex:
            cached_player = (
                self._cache.get(cache_key, None)
                if not long_term
                else self._long_term_cache.get(cache_key, None)
            )
            if cached_player is not None:
                return cached_player, False

            pending_player = PendingPlayer(username)

            if cache_key in self._cache:  # pragma: no coverage  # unreachable
                logger.error(f"Player {username} set to pending, but already exists")

            self._cache[cache_key] = self._long_term_cache[cache_key] = pending_player

            logger.debug(f"Player {username} not found in cache. Set to pending.")

            return pending_player, True

    def set_player_pending(self, username: str) -> PendingPlayer:
        """Note that this user is pending"""
        pending_player = PendingPlayer(username)

        cache_key = username.lower()

        with self._mutex:
            if cache_key in self._cache:
                logger.error(f"Player {username} set to pending, but already exists")

            self._cache[cache_key] = self._long_term_cache[cache_key] = pending_player

        return pending_player

    def set_cached_player(
        self,
        username: str,
        player: KnownPlayer | NickedPlayer | UnknownPlayer,
        genus: int,
    ) -> None:
        cache_key = username.lower()

        with self._mutex:
            if genus != self.current_genus:
                logger.warning(
                    f"Tried to store stats for {username} with old genus. Ignoring. "
                    f"{genus=}!={self.current_genus=}, {player=}"
                )
                return

            self._cache[cache_key] = self._long_term_cache[cache_key] = player

    def get_cached_player(
        self, username: str, *, long_term: bool = False
    ) -> Player | None:
        cache_key = username.lower()

        with self._mutex:
            return (
                self._cache.get(cache_key, None)
                if not long_term
                else self._long_term_cache.get(cache_key, None)
            )

    def update_cached_player(
        self, username: str, update: Callable[[KnownPlayer], KnownPlayer]
    ) -> None:
        """Update the cache for a player"""
        cache_key = username.lower()

        with self._mutex:
            player = self._cache.get(cache_key, None)
            if isinstance(player, KnownPlayer):
                self._cache[cache_key] = self._long_term_cache[cache_key] = update(
                    player
                )
            else:
                logger.warning(f"Player {username} not found during update")

    def uncache_player(self, username: str) -> None:
        """Clear the cache entry for `username`"""
        cache_key = username.lower()

        with self._mutex:
            self._cache.pop(cache_key, None)
            self._long_term_cache.pop(cache_key, None)

    def clear_cache(self, *, short_term_only: bool = False) -> None:
        """Clear the entire player cache"""
        with self._mutex:
            self.current_genus += 1
            self._cache.clear()
            if not short_term_only:
                self._long_term_cache.clear()
