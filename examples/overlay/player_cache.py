import logging
import threading
from typing import Callable

from cachetools import TTLCache

from examples.overlay.player import KnownPlayer, NickedPlayer, PendingPlayer, Player

logger = logging.getLogger(__name__)

# Session player cache
# Entries cached for 2mins, so they hopefully expire before the next queue
KNOWN_PLAYERS: TTLCache[str, Player] = TTLCache(maxsize=512, ttl=120)
STATS_MUTEX = threading.Lock()


def set_player_pending(username: str) -> PendingPlayer:
    """Note that this user is pending"""
    pending_player = PendingPlayer(username)

    with STATS_MUTEX:
        if username in KNOWN_PLAYERS:
            logger.error(f"Player {username} set to pending, but already exists")

        KNOWN_PLAYERS[username] = pending_player

    return pending_player


def set_cached_player(username: str, player: KnownPlayer | NickedPlayer) -> None:
    with STATS_MUTEX:
        KNOWN_PLAYERS[username] = player


def get_cached_player(username: str) -> Player | None:
    with STATS_MUTEX:
        return KNOWN_PLAYERS.get(username, None)


def update_cached_player(
    username: str, update: Callable[[KnownPlayer], KnownPlayer]
) -> None:
    """Update the cache for a player"""
    with STATS_MUTEX:
        player = KNOWN_PLAYERS.get(username, None)
        if isinstance(player, KnownPlayer):
            KNOWN_PLAYERS[username] = update(player)
        else:
            logger.warning(f"Player {username} not found during update")


def uncache_player(username: str) -> None:
    """Clear the cache entry for `username`"""
    with STATS_MUTEX:
        KNOWN_PLAYERS.pop(username, None)


def clear_cache() -> None:
    """Clear the entire player cache"""
    with STATS_MUTEX:
        KNOWN_PLAYERS.clear()
