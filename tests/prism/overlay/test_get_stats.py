import itertools
from collections.abc import Mapping
from dataclasses import dataclass, replace

import pytest

from prism.errors import APIError, PlayerNotFoundError
from prism.hypixel import create_known_player
from prism.overlay.controller import OverlayController
from prism.overlay.get_stats import denick, fetch_bedwars_stats, get_and_cache_stats
from prism.overlay.nick_database import NickDatabase
from prism.player import Account, KnownPlayer, NickedPlayer, UnknownPlayer
from tests.prism.overlay.utils import (
    MockedAccountProvider,
    MockedPlayerProvider,
    create_controller,
    make_player,
)

CURRENT_TIME_MS = 1234567890123


@dataclass(frozen=True)
class User:
    uuid: str
    username: str
    nick: str | None
    player: KnownPlayer | None


def make_user(username: str, player: bool, nick: str | None = None) -> User:
    return User(
        uuid=f"uuid-for-{username}",
        username=username,
        nick=nick,
        player=(
            make_player(
                variant="player",
                uuid=f"uuid-for-{username}",
                username=username,
                dataReceivedAtMs=CURRENT_TIME_MS,
            )
            if player
            else None
        ),
    )


def make_scenario_controller(*users: User) -> OverlayController:
    usernames = {user.username for user in users}
    uuids = {user.uuid for user in users}
    nicks = {user.nick for user in users}
    assert (
        len(usernames) == len(nicks) == len(uuids) == len(users)
    ), "Usernames, nicks, and uuids must be unique"

    username_table = {user.username: user for user in users}
    uuid_table = {user.uuid: user for user in users}
    nick_table = {user.nick: user.uuid for user in users if user.nick is not None}

    def get_account_by_username(username: str) -> Account:
        user = username_table.get(username, None)
        if user is None:
            raise PlayerNotFoundError("Player not found")

        return Account(uuid=user.uuid, username=user.username)

    def get_player(uuid: str, user_id: str) -> KnownPlayer:
        user = uuid_table.get(uuid, None)
        if user is None or user.player is None:
            raise PlayerNotFoundError("Player not found")

        return user.player

    controller = create_controller(
        account_provider=MockedAccountProvider(
            get_account_by_username=get_account_by_username
        ),
        player_provider=MockedPlayerProvider(get_player=get_player),
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
    "UnnickedPlayer": make_user(username="UnnickedPlayer", player=True),
    "NickedPlayer": make_user(username="NickedPlayer", nick="AmazingNick", player=True),
    "AmazingNick": make_user(username="AmazingNick", player=False),
    "MissingStats": make_user(username="MissingStats", player=False),
    "WrongPlayer": make_user(username="WrongPlayer", nick="SuperbNick", player=False),
    "SuperbNick": make_user(username="SuperbNick", player=False),
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
    {test_case[0] for test_case in fetch_bedwars_stats_cases}
), "Only scenario names from `scenarios` can be used"

assert set(scenarios).issubset(
    {test_case[0] for test_case in fetch_bedwars_stats_cases}
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
        assert user.player is not None
        player = replace(user.player, nick=user.nick if nicked else None)
    else:
        player = result

    assert (
        fetch_bedwars_stats(username=username, controller=scenarios[scenario_name])
        == player
    )


def test_fetch_bedwars_stats_wrong_displayname() -> None:
    wrong_user = User(
        uuid="fe3d80923dcf4147a35921f6b9fc460f",
        username="Summer173",
        nick=None,
        player=make_player(
            variant="player",
            uuid="fe3d80923dcf4147a35921f6b9fc460f",
            # The displayname on Hypixel is not correct, which should mean that this
            # player hasn't been on Hypixel for a while -> the person in the queue with
            # the name Summer173 must be a nick
            username="Sween_Sween",
            lastLoginMs=1641092163374,
            lastLogoutMs=1641092607085,
            dataReceivedAtMs=CURRENT_TIME_MS,
        ),
    )

    controller = make_scenario_controller(wrong_user)

    assert fetch_bedwars_stats("Summer173", controller) == NickedPlayer("Summer173")


def test_fetch_bedwars_stats_weird(ares_playerdata: Mapping[str, object]) -> None:
    ares = User(
        uuid="fffaceca46b24658b21f12c3cd2b413f",
        username="Ares",
        nick=None,
        player=create_known_player(
            dataReceivedAtMs=CURRENT_TIME_MS,
            playerdata=ares_playerdata,
            username="<missing name>",
            uuid="fffaceca46b24658b21f12c3cd2b413f",
        ),
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
        player=create_known_player(
            dataReceivedAtMs=CURRENT_TIME_MS,
            playerdata=ares_playerdata,
            username="<missing name>",
            uuid="fffaceca46b24658b21f12c3cd2b413f",
        ),
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


def test_get_and_cache_stats() -> None:
    controller = scenarios["nick"]
    user = users["NickedPlayer"]

    # For typing
    assert user.player is not None
    assert user.nick is not None

    nicked_player = replace(user.player, nick=user.nick)
    unnicked_player = user.player

    # Get the stats of the nicked player
    # Should get the stats and cache both the nicked and unnicked versions
    assert (
        get_and_cache_stats(username=user.nick, controller=controller) == nicked_player
    )

    assert controller.player_cache.get_cached_player(user.nick) == nicked_player
    assert controller.player_cache.get_cached_player(user.username) == unnicked_player


@pytest.mark.parametrize("clear", (True, False))
def test_get_and_cache_stats_cache_genus(clear: bool) -> None:
    my_username = "Player"
    my_uuid = "dead-beef"

    player = make_player(
        variant="player",
        uuid=my_uuid,
        username=my_username,
        dataReceivedAtMs=1234567,
    )

    def get_account_by_username(username: str) -> Account:
        assert username == my_username
        return Account(uuid=my_uuid, username=username)

    def get_player(uuid: str, user_id: str) -> KnownPlayer:
        assert uuid == my_uuid
        if clear:
            # While we were getting the playerdata, someone else cleared the cache
            controller.player_cache.clear_cache()

        return player

    controller = create_controller(
        account_provider=MockedAccountProvider(
            get_account_by_username=get_account_by_username
        ),
        player_provider=MockedPlayerProvider(get_player=get_player),
    )

    # We always return the stats even if the cache did not accept it
    assert get_and_cache_stats(username=my_username, controller=controller) == player

    # If the cache was cleared (and the genus incremented) it should not be stored
    assert controller.player_cache.get_cached_player(my_username) == (
        None if clear else player
    )


def test_fetch_bedwars_stats_error_during_uuid() -> None:
    def get_account_by_username(username: str) -> Account:
        raise APIError("Test error")

    controller = create_controller(
        account_provider=MockedAccountProvider(
            get_account_by_username=get_account_by_username
        )
    )

    assert fetch_bedwars_stats("someone", controller) == UnknownPlayer("someone")


def test_fetch_bedwars_stats_error_during_playerdata() -> None:
    def get_account_by_username(username: str) -> Account:
        return Account(username=username, uuid="uuid")

    def get_player(uuid: str, user_id: str) -> KnownPlayer:
        raise APIError("Test error")

    controller = create_controller(
        account_provider=MockedAccountProvider(
            get_account_by_username=get_account_by_username
        ),
        player_provider=MockedPlayerProvider(get_player=get_player),
    )

    assert fetch_bedwars_stats("someone", controller) == UnknownPlayer("someone")
