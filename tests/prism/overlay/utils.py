import threading
from collections.abc import Callable, Mapping, Set
from dataclasses import InitVar, dataclass, field, replace
from pathlib import Path, PurePath
from typing import Any, Literal, TypedDict, cast, overload

from cachetools import TTLCache

from prism.overlay.antisniper_api import AntiSniperAPIKeyHolder
from prism.overlay.controller import ProcessingError
from prism.overlay.nick_database import NickDatabase
from prism.overlay.output.config import (
    RatingConfigCollection,
    RatingConfigCollectionDict,
    safe_read_rating_config_collection_dict,
)
from prism.overlay.player import (
    KnownPlayer,
    NickedPlayer,
    PendingPlayer,
    Player,
    Stats,
    UnknownPlayer,
    Winstreaks,
)
from prism.overlay.player_cache import PlayerCache
from prism.overlay.settings import NickValue, Settings, fill_missing_settings
from prism.overlay.state import OverlayState
from prism.ratelimiting import RateLimiter

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
}
CUSTOM_RATING_CONFIG_COLLECTION = RatingConfigCollection.from_dict(
    CUSTOM_RATING_CONFIG_COLLECTION_DICT
)


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
) -> Player:
    if variant == "player":
        return KnownPlayer(
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
    out_of_sync: bool = False,
    in_queue: bool = False,
    own_username: str | None = OWN_USERNAME,
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
        out_of_sync=out_of_sync,
        in_queue=in_queue,
        own_username=own_username,
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
    antisniper_api_key: str | None = "placeholder-antisniper-key",
    use_antisniper_api: bool = False,
    user_id: str = "make-settings-default-user-id",
    known_nicks: dict[str, NickValue] | None = None,
    path: Path | PurePath | None = None,
) -> Settings:
    return Settings.from_dict(
        fill_missing_settings(
            {
                "user_id": user_id,
                "antisniper_api_key": antisniper_api_key,
                "use_antisniper_api": use_antisniper_api,
                "known_nicks": known_nicks or {},
            },
            2,
        )[0],
        path=cast(Path, path or PurePath("make_settings_settingsfile.json")),
    )


def missing_method(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError


class ExtraAttributes(TypedDict):
    antisniper_api_key: str | None
    redraw_event_set: bool
    update_presence_event_set: bool
    player_cache_data: TTLCache[str, Player]


@dataclass
class MockedController:
    """Class implementing the OverlayController protocol for testing"""

    api_key_invalid: bool = False
    api_key_throttled: bool = False
    antisniper_key_holder: AntiSniperAPIKeyHolder | None = field(
        init=False, repr=False, compare=False, hash=False
    )
    api_limiter: RateLimiter = field(
        default_factory=lambda: RateLimiter(limit=1, window=60),
        repr=False,
        compare=False,
        hash=False,
    )

    wants_shown: bool | None = None
    state: OverlayState = field(default_factory=create_state)
    settings: Settings = field(default_factory=make_settings)
    nick_database: NickDatabase = field(default_factory=lambda: NickDatabase([{}]))
    player_cache: PlayerCache = field(
        default_factory=PlayerCache, repr=False, compare=False, hash=False
    )

    redraw_event_set: InitVar[bool] = False
    redraw_event: threading.Event = field(
        init=False, repr=False, compare=False, hash=False
    )

    update_presence_event_set: InitVar[bool] = False
    update_presence_event: threading.Event = field(
        init=False, repr=False, compare=False, hash=False
    )

    state_mutex: threading.Lock = field(
        default_factory=threading.Lock, repr=False, compare=False, hash=False
    )

    get_uuid: Callable[[str], str | None | ProcessingError] = field(
        default=missing_method, repr=False, compare=False, hash=False
    )
    get_playerdata: Callable[[str], Mapping[str, object] | None | ProcessingError] = (
        field(default=missing_method, repr=False, compare=False, hash=False)
    )
    get_estimated_winstreaks: Callable[[str], tuple[Winstreaks, bool]] = field(
        default=missing_method, repr=False, compare=False, hash=False
    )

    _stored_settings: Settings | None = field(default=None, init=False)

    def __post_init__(
        self,
        redraw_event_set: bool,
        update_presence_event_set: bool,
    ) -> None:
        self.redraw_event = threading.Event()
        if redraw_event_set:
            self.redraw_event.set()

        self.update_presence_event = threading.Event()
        if update_presence_event_set:
            self.update_presence_event.set()

        self.antisniper_key_holder = (
            AntiSniperAPIKeyHolder(self.settings.antisniper_api_key)
            if self.settings.antisniper_api_key is not None
            else None
        )

    def store_settings(self) -> None:
        self._stored_settings = replace(self.settings)

    @property
    def extra(self) -> ExtraAttributes:
        return {
            "antisniper_api_key": (
                self.antisniper_key_holder.key
                if self.antisniper_key_holder is not None
                else None
            ),
            "redraw_event_set": self.redraw_event.is_set(),
            "update_presence_event_set": self.update_presence_event.is_set(),
            "player_cache_data": self.player_cache._cache,
        }
