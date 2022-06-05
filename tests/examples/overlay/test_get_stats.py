from examples.overlay.get_stats import (
    clear_cache,
    get_cached_stats,
    set_cached_stats,
    set_player_pending,
    uncache_stats,
    update_cached_stats,
)
from examples.overlay.player import NickedPlayer, PendingPlayer
from tests.examples.overlay.player_utils import make_player


def test_cache_manipulation() -> None:
    assert get_cached_stats("somependingplayer") is None

    # Setting a player to pending
    pending_player = set_player_pending("somependingplayer")
    assert isinstance(pending_player, PendingPlayer)
    assert get_cached_stats("somependingplayer") is pending_player

    # Uncaching a single player
    uncache_stats("somependingplayer")
    assert get_cached_stats("somependingplayer") is None

    # Setting the cache
    nicked_player = NickedPlayer("AmazingNick")
    set_cached_stats("somenickedplayer", nicked_player)
    assert get_cached_stats("somenickedplayer") is nicked_player

    # Setting a player to pending who is already known works, but issues a warning
    pending_player = set_player_pending("somenickedplayer")
    assert isinstance(pending_player, PendingPlayer)
    assert get_cached_stats("somenickedplayer") is pending_player

    # Updating a player
    original_player = make_player(username="joe")
    updated_player = make_player(username="joe", stars=200.1)

    assert original_player is not updated_player
    set_cached_stats("somerealplayer", original_player)
    assert get_cached_stats("somerealplayer") is original_player

    update_cached_stats("somerealplayer", lambda old: updated_player)
    assert get_cached_stats("somerealplayer") is updated_player

    # Updating a nonexistant player just issues a warning
    update_cached_stats("thisentrydoesnotexist", lambda old: updated_player)

    # Clearing the entire cache
    clear_cache()
    for ign in ("somependingplayer", "somenickedplayer", "somerealplayer"):
        assert get_cached_stats(ign) is None
