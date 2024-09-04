import queue

import pytest

from prism.overlay.controller import OverlayController
from prism.overlay.player import KnownPlayer, PendingPlayer, Player
from prism.overlay.player_cache import PlayerCache
from prism.overlay.threading import get_stat_list
from tests.prism.overlay.utils import (
    MockedController,
    create_state,
    make_player,
    make_settings,
)

EMPTY_QUEUE = queue.Queue[str]()


paul = make_player("player", "Paul")
kynes = make_player("player", "Liet", nick="Kynes")
liet = make_player("player", "Liet")
piter = make_player("nick", "Piter")
leto = make_player("pending", "Leto")


def make_player_cache(*players: Player) -> PlayerCache:
    cache = PlayerCache()
    for player in players:
        if isinstance(player, PendingPlayer):
            cache.set_player_pending(player.username)
            continue

        username = player.username
        if isinstance(player, KnownPlayer) and player.nick is not None:
            username = player.nick

        cache.set_cached_player(username, player, cache.current_genus)
    return cache


FULL_CACHE = make_player_cache(paul, kynes, liet, piter, leto)


def test_get_stat_list_no_redraw() -> None:
    assert get_stat_list(MockedController(), EMPTY_QUEUE, queue.Queue[str]()) is None


@pytest.mark.parametrize(
    "controller, expected_requested_stats, result",
    (
        # No players in the lobby
        (MockedController(), set(), []),
        (
            # Cache miss -> Request and return pending
            MockedController(state=create_state(lobby_players={"Paul"})),
            {"Paul"},
            [make_player("pending", "Paul")],
        ),
        # Different kinds of players
        (
            MockedController(
                state=create_state(lobby_players={"Paul"}), player_cache=FULL_CACHE
            ),
            set(),
            [paul],
        ),
        (
            MockedController(
                state=create_state(lobby_players={"Kynes"}), player_cache=FULL_CACHE
            ),
            set(),
            [kynes],
        ),
        (
            MockedController(
                state=create_state(lobby_players={"Liet"}), player_cache=FULL_CACHE
            ),
            set(),
            [liet],
        ),
        (
            MockedController(
                state=create_state(lobby_players={"Leto"}), player_cache=FULL_CACHE
            ),
            set(),
            [leto],
        ),
        (
            # Cache miss -> Request and return pending
            MockedController(state=create_state(lobby_players={"Leto"})),
            {"Leto"},
            [leto],
        ),
        (
            # Bunch of players, properly sorted
            MockedController(
                state=create_state(lobby_players={"Paul", "Kynes", "Piter", "Leto"}),
                player_cache=FULL_CACHE,
            ),
            set(),
            [piter, kynes, paul, leto],
        ),
        (
            # Only show alive players
            MockedController(
                settings=make_settings(hide_dead_players=True),
                state=create_state(
                    lobby_players={"Paul", "Kynes", "Piter", "Leto"},
                    alive_players={"Paul", "Kynes"},
                ),
                player_cache=FULL_CACHE,
            ),
            set(),
            [kynes, paul],
        ),
        (
            # Show all players
            MockedController(
                settings=make_settings(hide_dead_players=False),
                state=create_state(
                    lobby_players={"Paul", "Kynes", "Piter", "Leto"},
                    alive_players={"Paul", "Kynes"},
                ),
                player_cache=FULL_CACHE,
            ),
            set(),
            [piter, kynes, paul, leto],
        ),
        (
            # Sort correctly wrt party
            MockedController(
                state=create_state(
                    lobby_players={"Paul", "Kynes", "Piter", "Leto"},
                    party_members={"Piter", "Paul"},
                    own_username="Paul",
                ),
                player_cache=FULL_CACHE,
            ),
            set(),
            [kynes, leto, piter, paul],
        ),
        (
            # Cache miss on all
            MockedController(
                state=create_state(lobby_players={"Paul", "Kynes", "Piter", "Leto"}),
            ),
            {"Paul", "Kynes", "Piter", "Leto"},
            [
                make_player("pending", "Kynes"),
                make_player("pending", "Leto"),
                make_player("pending", "Paul"),
                make_player("pending", "Piter"),
            ],
        ),
        (
            # Duplicate nicked player
            MockedController(
                state=create_state(
                    lobby_players={"Liet", "Kynes"},
                    party_members={"Liet"},
                    own_username="Liet",
                ),
                player_cache=FULL_CACHE,
            ),
            set(),
            [kynes],
        ),
        (
            # Duplicate nicked player, but nicked is pending
            MockedController(
                state=create_state(
                    lobby_players={"Liet", "Kynes"},
                    party_members={"Liet"},
                    own_username="Liet",
                ),
                player_cache=make_player_cache(liet),
            ),
            {"Kynes"},
            # We don't know that Kynes denicks to Liet, so we show both
            [make_player("pending", "Kynes"), liet],
        ),
        (
            # Duplicate nicked player, but un-nicked is pending
            MockedController(
                state=create_state(
                    lobby_players={"Liet", "Kynes"},
                    party_members={"Liet"},
                    own_username="Liet",
                ),
                player_cache=make_player_cache(kynes),
            ),
            {"Liet"},
            # Even though Liet is still pending, we know that the username matches
            # with Kynes, so we can remove Liet
            [kynes],
        ),
    ),
)
def test_get_stat_list(
    controller: OverlayController,
    expected_requested_stats: set[str],
    result: list[Player],
) -> None:
    controller.redraw_event.set()

    requested_stats_queue = queue.Queue[str]()
    assert get_stat_list(controller, EMPTY_QUEUE, requested_stats_queue) == result
    requested_stats = set(
        requested_stats_queue.get_nowait() for _ in range(requested_stats_queue.qsize())
    )
    assert requested_stats == expected_requested_stats
