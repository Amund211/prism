import itertools
from dataclasses import dataclass
from typing import Any, Callable, TypedDict

import pytest

from examples.overlay.get_stats import create_known_player, fetch_bedwars_stats
from examples.overlay.player import KnownPlayer, NickedPlayer, Stats
from prism.calc import bedwars_level_from_exp

# Player data for a player who has been on Hypixel, but has not played bedwars
NEW_PLAYER_DATA: dict[str, Any] = {"stats": {}}


@dataclass(frozen=True)
class User:
    uuid: str
    username: str
    nick: str | None
    playerdata: dict[str, Any] | None


def make_user(username: str, playerdata: bool, nick: str | None = None) -> User:
    return User(
        uuid=f"uuid-for-{username}",
        username=username,
        nick=nick,
        playerdata={"displayname": username, **NEW_PLAYER_DATA} if playerdata else None,
    )


class Scenario(TypedDict):
    get_uuid: Callable[[str], str | None]
    get_player_data: Callable[[str], dict[str, Any] | None]
    denick: Callable[[str], str | None]


def make_scenario(*users: User) -> Scenario:
    usernames = set(user.username for user in users)
    uuids = set(user.uuid for user in users)
    nicks = set(user.nick for user in users)
    assert (
        len(usernames) == len(nicks) == len(uuids) == len(users)
    ), "Usernames, nicks, and uuids must be unique"

    username_table = {user.username: user for user in users}
    uuid_table = {user.uuid: user for user in users}
    nick_table = {user.nick: user for user in users}

    def get_uuid(username: str) -> str | None:
        user = username_table.get(username, None)
        return user.uuid if user is not None else None

    def get_player_data(uuid: str) -> dict[str, Any] | None:
        user = uuid_table.get(uuid, None)
        return user.playerdata if user is not None else None

    def denick(nick: str) -> str | None:
        user = nick_table.get(nick, None)
        return user.uuid if user is not None else None

    return Scenario(get_uuid=get_uuid, get_player_data=get_player_data, denick=denick)


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
    "simple": make_scenario(users["UnnickedPlayer"]),
    "nick": make_scenario(users["NickedPlayer"]),
    "nick_with_existing_user": make_scenario(
        users["NickedPlayer"], users["AmazingNick"]
    ),
    "nick_with_existing_user_no_data": make_scenario(
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
            playerdata=user.playerdata,
            username=user.username,
            uuid=user.uuid,
            nick=user.nick if nicked else None,
        )
    else:
        player = result

    assert fetch_bedwars_stats(username=username, **scenarios[scenario_name]) == player


def test_create_known_player(example_playerdata: dict[str, Any]) -> None:
    target = KnownPlayer(
        username="Technoblade",
        uuid="b876ec32e396476ba1158438d83c67d4",
        stars=bedwars_level_from_exp(1076936),
        stats=Stats(
            fkdr=20124 / 260,
            wlr=4924 / (5184 - 4924),
            winstreak=None,
            winstreak_accurate=False,
        ),
    )

    result = create_known_player(
        playerdata=example_playerdata,
        username="Technoblade",
        uuid="b876ec32e396476ba1158438d83c67d4",
        nick=None,
    )

    assert result == target
