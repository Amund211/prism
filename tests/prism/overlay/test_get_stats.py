import itertools
import unittest.mock
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pytest

from prism.errors import APIError, PlayerNotFoundError
from prism.hypixel import create_known_player
from prism.overlay.controller import OverlayController
from prism.overlay.get_stats import denick, fetch_bedwars_stats, get_bedwars_stats
from prism.overlay.nick_database import NickDatabase
from prism.player import KnownPlayer, NickedPlayer, UnknownPlayer
from tests.prism.overlay.utils import (
    MockedAccountProvider,
    MockedPlayerProvider,
    create_controller,
)

# Player data for a player who has been on Hypixel, but has not played bedwars
NEW_PLAYER_DATA: Mapping[str, object] = {"stats": {}}

CURRENT_TIME_MS = 1234567890123


@dataclass(frozen=True)
class User:
    uuid: str
    username: str
    nick: str | None
    playerdata: Mapping[str, object] | None


def make_user(username: str, playerdata: bool, nick: str | None = None) -> User:
    return User(
        uuid=f"uuid-for-{username}",
        username=username,
        nick=nick,
        playerdata={"displayname": username, **NEW_PLAYER_DATA} if playerdata else None,
    )


def make_scenario_controller(*users: User) -> OverlayController:
    usernames = set(user.username for user in users)
    uuids = set(user.uuid for user in users)
    nicks = set(user.nick for user in users)
    assert (
        len(usernames) == len(nicks) == len(uuids) == len(users)
    ), "Usernames, nicks, and uuids must be unique"

    username_table = {user.username: user for user in users}
    uuid_table = {user.uuid: user for user in users}
    nick_table = {user.nick: user.uuid for user in users if user.nick is not None}

    def get_uuid(username: str) -> str:
        user = username_table.get(username, None)
        if user is None:
            raise PlayerNotFoundError("Player not found")

        return user.uuid

    def get_playerdata(
        uuid: str, user_id: str, antisniper_key_holder: Any, api_limiter: Any
    ) -> Mapping[str, object]:
        user = uuid_table.get(uuid, None)
        if user is None or user.playerdata is None:
            raise PlayerNotFoundError("Player not found")
        return user.playerdata

    def get_time_ns() -> int:
        return CURRENT_TIME_MS * 1_000_000

    controller = create_controller(
        account_provider=MockedAccountProvider(get_uuid_for_username=get_uuid),
        player_provider=MockedPlayerProvider(get_playerdata_for_uuid=get_playerdata),
        get_time_ns=get_time_ns,
        nick_database=NickDatabase([nick_table]),
    )

    return controller


def test_denick() -> None:
    """Test the precedence of different denicking sources"""
    controller = create_controller()

    NICK = "AmazingNick"

    # No hits
    assert denick(NICK, controller) is None

    # Hit in database
    controller.nick_database.databases.append({NICK: "database-uuid"})
    assert denick(NICK, controller) == "database-uuid"

    # Hit in default database
    controller.nick_database.default_database[NICK] = "default-database-uuid"
    assert denick(NICK, controller) == "default-database-uuid"


users = {
    "UnnickedPlayer": make_user(username="UnnickedPlayer", playerdata=True),
    "NickedPlayer": make_user(
        username="NickedPlayer", nick="AmazingNick", playerdata=True
    ),
    "AmazingNick": make_user(username="AmazingNick", playerdata=False),
    "MissingStats": make_user(username="MissingStats", playerdata=False),
    "WrongPlayer": make_user(
        username="WrongPlayer", nick="SuperbNick", playerdata=False
    ),
    "SuperbNick": make_user(username="SuperbNick", playerdata=False),
}

scenarios = {
    "simple": make_scenario_controller(users["UnnickedPlayer"]),
    "nick": make_scenario_controller(users["NickedPlayer"]),
    "nick_with_existing_user": make_scenario_controller(
        users["NickedPlayer"], users["AmazingNick"]
    ),
    "nick_with_existing_user_no_data": make_scenario_controller(
        users["WrongPlayer"], users["SuperbNick"]
    ),
}


fetch_bedwars_stats_cases: tuple[
    tuple[str, str, tuple[User, bool] | NickedPlayer], ...
] = (
    ("simple", "AmazingNick", NickedPlayer("AmazingNick")),
    ("simple", "UnnickedPlayer", (users["UnnickedPlayer"], False)),
    ("nick", "UnnickedPlayer", NickedPlayer("UnnickedPlayer")),
    ("nick", "NickedPlayer", (users["NickedPlayer"], False)),
    ("nick", "AmazingNick", (users["NickedPlayer"], True)),
    ("nick_with_existing_user", "NickedPlayer", (users["NickedPlayer"], False)),
    ("nick_with_existing_user", "AmazingNick", (users["NickedPlayer"], True)),
    ("nick_with_existing_user_no_data", "WrongPlayer", NickedPlayer("WrongPlayer")),
    ("nick_with_existing_user_no_data", "SuperbNick", NickedPlayer("SuperbNick")),
)

assert set(scenarios).issuperset(
    set(test_case[0] for test_case in fetch_bedwars_stats_cases)
), "Only scenario names from `scenarios` can be used"

assert set(scenarios).issubset(
    set(test_case[0] for test_case in fetch_bedwars_stats_cases)
), "All scenarios must be used"


@pytest.mark.parametrize(
    "scenario_name, username, result",
    fetch_bedwars_stats_cases,
    ids=tuple(
        itertools.starmap(
            lambda scenario_name, username, player: f"{scenario_name}: {username}",
            fetch_bedwars_stats_cases,
        )
    ),
)
def test_fetch_bedwars_stats(
    scenario_name: str, username: str, result: tuple[User, bool] | NickedPlayer
) -> None:
    player: KnownPlayer | NickedPlayer
    if isinstance(result, tuple):
        user, nicked = result
        assert user.playerdata is not None
        player = create_known_player(
            dataReceivedAtMs=CURRENT_TIME_MS,
            playerdata=user.playerdata,
            username=user.username,
            uuid=user.uuid,
            nick=user.nick if nicked else None,
        )
    else:
        player = result

    assert (
        fetch_bedwars_stats(username=username, controller=scenarios[scenario_name])
        == player
    )


def test_fetch_bedwars_stats_wrong_displayname(
    technoblade_playerdata: Mapping[str, object],
) -> None:
    wrong_user = User(
        uuid="fe3d80923dcf4147a35921f6b9fc460f",
        username="Summer173",
        nick=None,
        playerdata={
            "_id": "61bc6102941308034eb5121f",
            "uuid": "fe3d80923dcf4147a35921f6b9fc460f",
            # The displayname on Hypixel is not correct, which should mean that this
            # player hasn't been on Hypixel for a while -> the person in the queue with
            # the name Summer173 must be a nick
            "displayname": "Sween_Sween",
            "firstLogin": 1639735554687,
            "lastLogin": 1641092163374,
            "playername": "sween_sween",
            # Patch in some actual stats so we know we're testing the right thing
            "stats": technoblade_playerdata["stats"],
            "lastLogout": 1641092607085,
            "networkExp": 99720,
        },
    )

    controller = make_scenario_controller(wrong_user)

    assert fetch_bedwars_stats("Summer173", controller) == NickedPlayer("Summer173")


def test_fetch_bedwars_stats_weird(ares_playerdata: Mapping[str, object]) -> None:
    ares = User(
        uuid="fffaceca46b24658b21f12c3cd2b413f",
        username="Ares",
        nick=None,
        playerdata=ares_playerdata,
    )
    controller = make_scenario_controller(ares)

    # Since the displayname field is missing from their stats, it will not match Ares,
    # and we assume it is a nick.
    target = NickedPlayer("Ares")

    assert fetch_bedwars_stats("Ares", controller) == target


def test_fetch_bedwars_stats_weird_nicked(
    ares_playerdata: Mapping[str, object],
) -> None:
    ares = User(
        uuid="fffaceca46b24658b21f12c3cd2b413f",
        username="Ares",
        nick="CrazyNick",
        playerdata=ares_playerdata,
    )
    controller = make_scenario_controller(ares)

    # Since we get the uuid from a denick we do not know a username, and cannot verify
    # that they are a real player. We therefore trust the playerdata to be real.
    target = create_known_player(
        dataReceivedAtMs=CURRENT_TIME_MS,
        playerdata=ares_playerdata,
        username="<missing name>",  # We rely on Hypixel to provide us the username
        uuid=ares.uuid,
        nick="CrazyNick",
    )

    assert fetch_bedwars_stats("CrazyNick", controller) == target


def test_get_bedwars_stats() -> None:
    controller = scenarios["nick"]
    user = users["NickedPlayer"]

    # For typing
    assert user.playerdata is not None
    assert user.nick is not None

    nicked_player = create_known_player(
        dataReceivedAtMs=CURRENT_TIME_MS,
        playerdata=user.playerdata,
        username=user.username,
        uuid=user.uuid,
        nick=user.nick,
    )
    unnicked_player = create_known_player(
        dataReceivedAtMs=CURRENT_TIME_MS,
        playerdata=user.playerdata,
        username=user.username,
        uuid=user.uuid,
        nick=None,
    )

    # Get the stats of the nicked player
    # Should get the stats and cache both the nicked and unnicked versions
    assert get_bedwars_stats(username=user.nick, controller=controller) == nicked_player

    # Getting both the nicked and unnicked stats now should just go to cache
    with unittest.mock.patch(
        "prism.overlay.get_stats.fetch_bedwars_stats"
    ) as patched_fetch_stats:
        assert (
            get_bedwars_stats(username=user.nick, controller=controller)
            == nicked_player
        )
        patched_fetch_stats.assert_not_called()

        assert (
            get_bedwars_stats(username=user.username, controller=controller)
            == unnicked_player
        )
        patched_fetch_stats.assert_not_called()


@pytest.mark.parametrize("clear", (True, False))
def test_get_bedwars_stats_cache_genus(clear: bool) -> None:
    my_username = "Player"
    my_uuid = "dead-beef"
    my_player_data: Mapping[str, object] = {
        "displayname": my_username,
        **NEW_PLAYER_DATA,
    }

    def get_uuid(username: str) -> str:
        assert username == my_username
        return my_uuid

    def get_playerdata(
        uuid: str, user_id: str, antisniper_key_holder: Any, api_limiter: Any
    ) -> Mapping[str, object]:
        assert uuid == my_uuid
        if clear:
            # While we were getting the playerdata, someone else cleared the cache
            controller.player_cache.clear_cache()
        return my_player_data

    def get_time_ns() -> int:
        return 1234567 * 1_000_000

    controller = create_controller(
        account_provider=MockedAccountProvider(get_uuid_for_username=get_uuid),
        player_provider=MockedPlayerProvider(get_playerdata_for_uuid=get_playerdata),
        get_time_ns=get_time_ns,
    )

    player = create_known_player(
        dataReceivedAtMs=1234567,
        playerdata=my_player_data,
        username=my_username,
        uuid=my_uuid,
    )

    # We always return the stats even if the cache did not accept it
    assert get_bedwars_stats(username=my_username, controller=controller) == player

    # If the cache was cleared (and the genus incremented) it should not be stored
    assert controller.player_cache.get_cached_player(my_username) == (
        None if clear else player
    )


def test_fetch_bedwars_stats_error_during_uuid() -> None:
    def get_uuid(username: str) -> str:
        raise APIError("Test error")

    controller = create_controller(
        account_provider=MockedAccountProvider(get_uuid_for_username=get_uuid)
    )

    assert fetch_bedwars_stats("someone", controller) == UnknownPlayer("someone")


def test_fetch_bedwars_stats_error_during_playerdata() -> None:
    def get_uuid(username: str) -> str:
        return "uuid"

    def get_playerdata(
        uuid: str, user_id: str, antisniper_key_holder: Any, api_limiter: Any
    ) -> Mapping[str, object]:
        raise APIError("Test error")

    def get_time_ns() -> int:
        return CURRENT_TIME_MS * 1_000_000

    controller = create_controller(
        account_provider=MockedAccountProvider(get_uuid_for_username=get_uuid),
        player_provider=MockedPlayerProvider(get_playerdata_for_uuid=get_playerdata),
        get_time_ns=get_time_ns,
    )

    assert fetch_bedwars_stats("someone", controller) == UnknownPlayer("someone")
