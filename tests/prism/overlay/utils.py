import io
import queue
from collections.abc import Callable, Set
from pathlib import Path, PurePath
from typing import Any, Iterable, Literal, TextIO, TypeVar, cast, overload

from prism.overlay.controller import (
    AccountProvider,
    OverlayController,
    PlayerProvider,
    TagsProvider,
    WinstreakProvider,
)
from prism.overlay.keybinds import Key
from prism.overlay.nick_database import NickDatabase
from prism.overlay.output.config import (
    RatingConfigCollection,
    RatingConfigCollectionDict,
    safe_read_rating_config_collection_dict,
)
from prism.overlay.player_cache import PlayerCache
from prism.overlay.settings import NickValue, Settings, fill_missing_settings
from prism.overlay.state import OverlayState
from prism.player import (
    Account,
    KnownPlayer,
    NickedPlayer,
    PendingPlayer,
    Player,
    Stats,
    Tags,
    UnknownPlayer,
    Winstreaks,
)

# Username set by default in create_state
OWN_USERNAME = "OwnUsername"

DEFAULT_RATING_CONFIG_COLLECTION_DICT, _ = safe_read_rating_config_collection_dict({})
DEFAULT_RATING_CONFIG_COLLECTION = RatingConfigCollection.from_dict(
    DEFAULT_RATING_CONFIG_COLLECTION_DICT
)

CUSTOM_RATING_CONFIG_COLLECTION_DICT: RatingConfigCollectionDict = {
    "stars": {
        "type": "level_based",
        "rate_by_level": True,
        "decimals": 0,
        "levels": (300.0, 600.0, 900.0, 1200.0),
        "sort_ascending": True,
    },
    "index": {
        "type": "level_based",
        "rate_by_level": False,
        "decimals": 1,
        "levels": (1000.0, 10_000.0, 16_000.0, 64_000.0),
        "sort_ascending": False,
    },
    "fkdr": {
        "type": "level_based",
        "rate_by_level": False,
        "decimals": 4,
        "levels": (1.0, 4.0, 16.0, 64.0),
        "sort_ascending": True,
    },
    "kdr": {
        "type": "level_based",
        "rate_by_level": False,
        "decimals": 3,
        "levels": (2.0, 4.0, 16.0, 64.0),
        "sort_ascending": False,
    },
    "bblr": {
        "type": "level_based",
        "rate_by_level": False,
        "decimals": 0,
        "levels": (1.0, 4.0, 16.0, 64.0),
        "sort_ascending": True,
    },
    "wlr": {
        "type": "level_based",
        "rate_by_level": False,
        "decimals": 1,
        "levels": (0.25, 0.5, 1.0, 2.0),
        "sort_ascending": False,
    },
    "winstreak": {
        "type": "level_based",
        "rate_by_level": False,
        "decimals": 0,
        "levels": (2.0, 5.0, 10.0, 100.0),
        "sort_ascending": True,
    },
    "kills": {
        "type": "level_based",
        "rate_by_level": False,
        "decimals": 3,
        "levels": (2.1, 5.3, 12.0, 150.0),
        "sort_ascending": False,
    },
    "finals": {
        "type": "level_based",
        "rate_by_level": False,
        "decimals": 2,
        "levels": (6.0, 9.0, 10.0, 1000.0),
        "sort_ascending": True,
    },
    "beds": {
        "type": "level_based",
        "rate_by_level": False,
        "decimals": 1,
        "levels": (1.0, 5.0, 15.0, 200.0),
        "sort_ascending": False,
    },
    "wins": {
        "type": "level_based",
        "rate_by_level": False,
        "decimals": 3,
        "levels": (1.0, 10.0, 11.0, 120.0),
        "sort_ascending": True,
    },
    "sessiontime": {
        "type": "level_based",
        "rate_by_level": True,
        "decimals": 0,
        "levels": (300.0, 120.0, 60.0, 30.0),
        "sort_ascending": True,
    },
}
CUSTOM_RATING_CONFIG_COLLECTION = RatingConfigCollection.from_dict(
    CUSTOM_RATING_CONFIG_COLLECTION_DICT
)


def no_close(file: io.StringIO) -> io.StringIO:
    """Monkeypatch StringIO to not close - discarding the contents"""
    file.close = lambda: None  # type: ignore[method-assign]

    return file


def make_dead_path(path_str: str) -> Path:
    """
    Return a PurePath instance disguised as a Path

    This asserts that the Path instance is not used for disk access
    """
    return cast(Path, PurePath(path_str))


@overload
def make_player(variant: Literal["unknown"], username: str = ...) -> UnknownPlayer: ...


@overload
def make_player(variant: Literal["nick"], username: str = ...) -> NickedPlayer: ...


@overload
def make_player(variant: Literal["pending"], username: str = ...) -> PendingPlayer: ...


@overload
def make_player(
    variant: Literal["player"] = "player",
    username: str = ...,
    fkdr: float = ...,
    stars: float = ...,
    kdr: float = ...,
    bblr: float = ...,
    wlr: float = ...,
    winstreak: int | None = ...,
    winstreak_accurate: bool = ...,
    kills: int = ...,
    finals: int = ...,
    beds: int = ...,
    wins: int = ...,
    nick: str | None = ...,
    uuid: str = ...,
    lastLoginMs: int | None = ...,
    lastLogoutMs: int | None = ...,
    dataReceivedAtMs: int = ...,
    tags: Tags | None = None,
) -> KnownPlayer: ...


def make_player(
    variant: Literal["unknown", "nick", "pending", "player"] = "player",
    username: str = "player",
    fkdr: float = 0.0,
    stars: float = 1.0,
    kdr: float = 0.0,
    bblr: float = 0.0,
    wlr: float = 0.0,
    winstreak: int | None = None,
    winstreak_accurate: bool = False,
    kills: int = 0,
    finals: int = 0,
    beds: int = 0,
    wins: int = 0,
    nick: str | None = None,
    uuid: str = "placeholder",
    lastLoginMs: int | None = None,
    lastLogoutMs: int | None = None,
    dataReceivedAtMs: int = 1234567890,
    tags: Tags | None = Tags(sniping="none", cheating="none"),
) -> Player:
    if variant == "player":
        return KnownPlayer(
            dataReceivedAtMs=dataReceivedAtMs,
            stars=stars,
            stats=Stats(
                index=stars * fkdr**2,
                fkdr=fkdr,
                kdr=kdr,
                bblr=bblr,
                wlr=wlr,
                winstreak=winstreak,
                winstreak_accurate=winstreak_accurate,
                kills=kills,
                finals=finals,
                beds=beds,
                wins=wins,
            ),
            username=username,
            nick=nick,
            uuid=uuid,
            lastLoginMs=lastLoginMs,
            lastLogoutMs=lastLogoutMs,
            tags=tags,
        )
    elif variant == "unknown":
        return UnknownPlayer(username)
    elif variant == "nick":
        assert nick is None, "Provide the nick as the username"
        return NickedPlayer(nick=username)
    elif variant == "pending":
        return PendingPlayer(username=username)


def create_state(
    party_members: Set[str] | None = None,
    lobby_players: Set[str] = frozenset(),
    alive_players: Set[str] | None = None,
    last_game_start: float | None = None,
    out_of_sync: bool = False,
    in_queue: bool = False,
    own_username: str | None = OWN_USERNAME,
    now_func: Callable[[], float] = lambda: 0,
) -> OverlayState:
    if party_members is None:
        party_members = (
            frozenset() if own_username is None else frozenset([own_username])
        )

    if own_username is not None:
        assert own_username in party_members, f"{own_username} must be in the party"

    return OverlayState(
        party_members=frozenset(party_members),
        lobby_players=frozenset(lobby_players),
        alive_players=(
            frozenset(alive_players)
            if alive_players is not None
            else frozenset(lobby_players)
        ),
        last_game_start=last_game_start,
        out_of_sync=out_of_sync,
        in_queue=in_queue,
        own_username=own_username,
        now_func=now_func,
    )


def make_winstreaks(
    overall: int | None = None,
    solo: int | None = None,
    doubles: int | None = None,
    threes: int | None = None,
    fours: int | None = None,
) -> Winstreaks:
    return Winstreaks(
        overall=overall, solo=solo, doubles=doubles, threes=threes, fours=fours
    )


def make_settings(
    urchin_api_key: str | None = None,
    user_id: str = "make-settings-default-user-id",
    known_nicks: dict[str, NickValue] | None = None,
    hide_dead_players: bool | None = None,
    autowho: bool | None = None,
    autowho_delay: float | None = None,
    chat_hotkey: Key | None = None,
    activate_in_bedwars_duels: bool | None = None,
    write_settings_file_utf8: Callable[[], TextIO] = lambda: io.StringIO(),
) -> Settings:
    return Settings.from_dict(
        fill_missing_settings(
            {
                "user_id": user_id,
                "urchin_api_key": urchin_api_key,
                "known_nicks": known_nicks or {},
                "hide_dead_players": hide_dead_players,
                "autowho": autowho,
                "autowho_delay": autowho_delay,
                "chat_hotkey": (
                    chat_hotkey.to_dict() if chat_hotkey is not None else None
                ),
                "activate_in_bedwars_duels": activate_in_bedwars_duels,
            },
            2,
        )[0],
        write_settings_file_utf8=write_settings_file_utf8,
    )


def assert_not_called(*args: Any, **kwargs: Any) -> Any:
    """Test helper that asserts that the method is not called."""
    assert False, "This function should not have been called"


class MockedAccountProvider:
    def __init__(self, get_account_by_username: Callable[[str], Account]) -> None:
        self._get_account_by_username = get_account_by_username

    def get_account_by_username(self, username: str, *, user_id: str) -> Account:
        return self._get_account_by_username(username)


class MockedPlayerProvider:
    def __init__(
        self,
        get_player: Callable[
            [str, str],
            KnownPlayer,
        ],
        seconds_until_unblocked: float = 0.0,
    ) -> None:
        self._get_player = get_player
        self._seconds_until_unblocked = seconds_until_unblocked

    def get_player(
        self,
        uuid: str,
        user_id: str,
    ) -> KnownPlayer:
        return self._get_player(uuid, user_id)

    @property
    def seconds_until_unblocked(self) -> float:
        return self._seconds_until_unblocked


class MockedWinstreakProvider:
    def __init__(
        self,
        get_estimated_winstreaks_for_uuid: Callable[
            [str],
            tuple[Winstreaks, bool],
        ] = lambda uuid: (make_winstreaks(), False),
        seconds_until_unblocked: float = 0.0,
    ) -> None:
        self._get_estimated_winstreaks_for_uuid = get_estimated_winstreaks_for_uuid
        self._seconds_until_unblocked = seconds_until_unblocked

    def get_estimated_winstreaks_for_uuid(self, uuid: str) -> tuple[Winstreaks, bool]:
        return self._get_estimated_winstreaks_for_uuid(uuid)

    @property
    def seconds_until_unblocked(self) -> float:
        return self._seconds_until_unblocked


class MockedTagsProvider:
    def __init__(
        self,
        get_tags: Callable[
            [str, str, str | None],
            Tags,
        ],
        seconds_until_unblocked: float = 0.0,
    ) -> None:
        self._get_tags = get_tags
        self._seconds_until_unblocked = seconds_until_unblocked

    def get_tags(
        self,
        uuid: str,
        user_id: str,
        urchin_api_key: str | None = None,
    ) -> Tags:
        return self._get_tags(uuid, user_id, urchin_api_key)

    @property
    def seconds_until_unblocked(self) -> float:
        return self._seconds_until_unblocked


def create_controller(
    state: OverlayState | None = None,
    settings: Settings | None = None,
    wants_shown: bool | None = None,
    urchin_api_key_invalid: bool = False,
    missing_local_issuer_certificate: bool = False,
    ready: bool = True,
    autowho_event_set: bool = False,
    redraw_event_set: bool = False,
    update_presence_event_set: bool = False,
    update_available_event_set: bool = False,
    current_player_updates: Iterable[KnownPlayer] | None = None,
    player_cache: PlayerCache | None = None,
    nick_database: NickDatabase | None = None,
    account_provider: AccountProvider = MockedAccountProvider(assert_not_called),
    player_provider: PlayerProvider = MockedPlayerProvider(assert_not_called),
    winstreak_provider: WinstreakProvider = MockedWinstreakProvider(assert_not_called),
    tags_provider: TagsProvider = MockedTagsProvider(assert_not_called),
) -> OverlayController:
    controller = OverlayController(
        state=state or create_state(),
        settings=settings or make_settings(),
        nick_database=nick_database or NickDatabase([{}]),
        account_provider=account_provider,
        player_provider=player_provider,
        winstreak_provider=winstreak_provider,
        tags_provider=tags_provider,
    )

    controller.wants_shown = wants_shown
    controller.urchin_api_key_invalid = urchin_api_key_invalid
    controller.missing_local_issuer_certificate = missing_local_issuer_certificate
    controller.ready = ready

    if autowho_event_set:
        controller.autowho_event.set()
    if redraw_event_set:
        controller.redraw_event.set()
    if update_presence_event_set:
        controller.update_presence_event.set()
    if update_available_event_set:
        controller.update_available_event.set()

    if player_cache is not None:
        controller.player_cache = player_cache

    if current_player_updates is not None:
        for player in current_player_updates:
            controller.current_player_updates_queue.put_nowait(player)

    return controller


T = TypeVar("T")


def get_queue_contents(q: queue.Queue[T]) -> tuple[T, ...]:
    contents = []
    while not q.empty():
        contents.append(q.get_nowait())
    for item in contents:
        q.put_nowait(item)
    return tuple(contents)


def assert_controllers_equal(
    controller1: OverlayController,
    controller2: OverlayController,
    /,
    *,
    ignore_player_cache: bool = False,
) -> None:
    assert controller1.urchin_api_key_invalid == controller2.urchin_api_key_invalid
    assert (
        controller1.missing_local_issuer_certificate
        == controller2.missing_local_issuer_certificate
    )

    assert controller1.wants_shown == controller2.wants_shown
    assert controller1.ready == controller2.ready
    assert controller1.state == controller2.state
    assert controller1.settings == controller2.settings
    assert controller1.nick_database == controller2.nick_database

    assert controller1.autowho_event.is_set() == controller2.autowho_event.is_set()
    assert controller1.redraw_event.is_set() == controller2.redraw_event.is_set()
    assert (
        controller1.update_presence_event.is_set()
        == controller2.update_presence_event.is_set()
    )
    assert (
        controller1.update_available_event.is_set()
        == controller2.update_available_event.is_set()
    )

    if not ignore_player_cache:
        assert controller1.player_cache._cache == controller2.player_cache._cache

    assert get_queue_contents(
        controller1.current_player_updates_queue
    ) == get_queue_contents(controller2.current_player_updates_queue)
