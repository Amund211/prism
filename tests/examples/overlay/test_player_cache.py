from examples.overlay.player import NickedPlayer, PendingPlayer
from examples.overlay.player_cache import PlayerCache
from tests.examples.overlay.utils import make_player


def test_cache_manipulation() -> None:
    player_cache = PlayerCache()
    assert player_cache.get_cached_player("somependingplayer") is None

    # Setting a player to pending
    pending_player = player_cache.set_player_pending("somependingplayer")
    assert isinstance(pending_player, PendingPlayer)
    assert player_cache.get_cached_player("somependingplayer") is pending_player

    # Uncaching a single player
    player_cache.uncache_player("somependingplayer")
    assert player_cache.get_cached_player("somependingplayer") is None

    # Setting the cache
    nicked_player = NickedPlayer("AmazingNick")
    player_cache.set_cached_player("somenickedplayer", nicked_player)
    assert player_cache.get_cached_player("somenickedplayer") is nicked_player

    # Setting a player to pending who is already known works, but issues a warning
    pending_player = player_cache.set_player_pending("somenickedplayer")
    assert isinstance(pending_player, PendingPlayer)
    assert player_cache.get_cached_player("somenickedplayer") is pending_player

    # Updating a player
    original_player = make_player(username="joe")
    updated_player = make_player(username="joe", stars=200.1)

    assert original_player is not updated_player
    player_cache.set_cached_player("somerealplayer", original_player)
    assert player_cache.get_cached_player("somerealplayer") is original_player

    player_cache.update_cached_player("somerealplayer", lambda old: updated_player)
    assert player_cache.get_cached_player("somerealplayer") is updated_player

    # Updating a nonexistant player just issues a warning
    player_cache.update_cached_player(
        "thisentrydoesnotexist", lambda old: updated_player
    )

    # Clearing the entire cache
    player_cache.clear_cache()
    for ign in ("somependingplayer", "somenickedplayer", "somerealplayer"):
        assert player_cache.get_cached_player(ign) is None
