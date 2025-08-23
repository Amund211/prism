from prism.overlay.player_cache import PlayerCache
from prism.player import NickedPlayer, PendingPlayer
from tests.prism.overlay.utils import make_player


def test_cache_manipulation() -> None:
    player_cache = PlayerCache()
    assert player_cache.get_cached_player("somependingplayer") is None
    assert player_cache.get_cached_player("somependingplayer", long_term=True) is None

    # Setting a player to pending
    pending_player = player_cache.set_player_pending("somependingplayer")
    assert isinstance(pending_player, PendingPlayer)
    assert player_cache.get_cached_player("somependingplayer") is pending_player
    assert (
        player_cache.get_cached_player("somependingplayer", long_term=True)
        is pending_player
    )

    # Uncaching a single player
    player_cache.uncache_player("somependingplayer")
    assert player_cache.get_cached_player("somependingplayer") is None
    assert player_cache.get_cached_player("somependingplayer", long_term=True) is None

    # Setting the cache
    nicked_player = NickedPlayer("AmazingNick")
    player_cache.set_cached_player("somenickedplayer", nicked_player, genus=0)
    assert player_cache.get_cached_player("somenickedplayer") is nicked_player
    assert (
        player_cache.get_cached_player("somenickedplayer", long_term=True)
        is nicked_player
    )

    # Setting a player to pending who is already known works, but issues a warning
    pending_player = player_cache.set_player_pending("somenickedplayer")
    assert isinstance(pending_player, PendingPlayer)
    assert player_cache.get_cached_player("somenickedplayer") is pending_player
    assert (
        player_cache.get_cached_player("somenickedplayer", long_term=True)
        is pending_player
    )

    # Updating a player
    original_player = make_player(username="joe")
    updated_player = make_player(username="joe", stars=200.1)

    assert original_player is not updated_player
    player_cache.set_cached_player("somerealplayer", original_player, genus=0)
    assert player_cache.get_cached_player("somerealplayer") is original_player
    assert (
        player_cache.get_cached_player("somerealplayer", long_term=True)
        is original_player
    )

    player_cache.update_cached_player("somerealplayer", lambda old: updated_player)
    assert player_cache.get_cached_player("somerealplayer") is updated_player
    assert (
        player_cache.get_cached_player("somerealplayer", long_term=True)
        is updated_player
    )

    # Updating a nonexistant player just issues a warning
    player_cache.update_cached_player(
        "thisentrydoesnotexist", lambda old: updated_player
    )

    # Clearing the entire cache
    player_cache.clear_cache()
    for ign in ("somependingplayer", "somenickedplayer", "somerealplayer"):
        assert player_cache.get_cached_player(ign) is None
        assert player_cache.get_cached_player(ign, long_term=True) is None

    pending_player = player_cache.set_player_pending("somependingplayer")

    # Clearing only the short term cache
    player_cache.clear_cache(short_term_only=True)
    assert player_cache.get_cached_player("somependingplayer") is None
    assert (
        player_cache.get_cached_player("somependingplayer", long_term=True)
        is pending_player
    )


def test_cache_genus() -> None:
    """
    Test the behaviour of the cache genus

    When we make a request to Hypixel we note the cache genus at that time.
    After the request has finished we store the result with the old genus.
    If the genus has been updated in the mean time due to a cache clear, the result
    should not be stored.
    """
    player_cache = PlayerCache()

    # Starting one request
    genus_1 = player_cache.current_genus

    # Clearing the entire cache
    player_cache.clear_cache()

    # Starting another request
    genus_2 = player_cache.current_genus

    # Request 1 finishes
    amazing_nick = NickedPlayer("AmazingNick")
    player_cache.set_cached_player("AmazingNick", amazing_nick, genus=genus_1)

    # Request 2 finishes
    other_nick = NickedPlayer("OtherNick")
    player_cache.set_cached_player("OtherNick", other_nick, genus=genus_2)

    assert player_cache.get_cached_player("AmazingNick") is None
    assert player_cache.get_cached_player("OtherNick") is other_nick
