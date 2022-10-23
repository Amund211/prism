import threading
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal, overload

from prism.overlay.nick_database import NickDatabase
from prism.overlay.player import (
    KnownPlayer,
    NickedPlayer,
    PendingPlayer,
    Player,
    Stats,
    Winstreaks,
)
from prism.overlay.player_cache import PlayerCache
from prism.overlay.settings import NickValue, Settings, fill_missing_settings
from prism.overlay.state import OverlayState

# Username set by default in create_state
OWN_USERNAME = "OwnUsername"


@overload
def make_player(variant: Literal["nick"], username: str = ...) -> NickedPlayer:
    ...


@overload
def make_player(variant: Literal["pending"], username: str = ...) -> PendingPlayer:
    ...


@overload
def make_player(
    variant: Literal["player"] = "player",
    username: str = ...,
    fkdr: float = ...,
    stars: float = ...,
    wlr: float = ...,
    winstreak: int | None = ...,
    winstreak_accurate: bool = ...,
    nick: str | None = ...,
    uuid: str = ...,
) -> KnownPlayer:
    ...


def make_player(
    variant: Literal["nick", "pending", "player"] = "player",
    username: str = "player",
    fkdr: float = 0.0,
    stars: float = 1.0,
    wlr: float = 0.0,
    winstreak: int | None = None,
    winstreak_accurate: bool = False,
    nick: str | None = None,
    uuid: str = "placeholder",
) -> Player:
    if variant == "player":
        return KnownPlayer(
            stars=stars,
            stats=Stats(
                fkdr=fkdr,
                wlr=wlr,
                winstreak=winstreak,
                winstreak_accurate=winstreak_accurate,
            ),
            username=username,
            nick=nick,
            uuid=uuid,
        )
    elif variant == "nick":
        assert nick is None, "Provide the nick as the username"
        return NickedPlayer(nick=username)
    elif variant == "pending":
        return PendingPlayer(username=username)


def create_state(
    party_members: set[str] = set(),
    lobby_players: set[str] = set(),
    out_of_sync: bool = False,
    in_queue: bool = False,
    own_username: str | None = OWN_USERNAME,
) -> OverlayState:
    yourself = set() if own_username is None else set([own_username])
    return OverlayState(
        party_members=party_members | yourself,
        lobby_players=lobby_players,
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
    hypixel_api_key: str = "placeholder-hypixel-key",
    antisniper_api_key: str | None = None,
    use_antisniper_api: bool = False,
    known_nicks: dict[str, NickValue] | None = None,
    path: Path | None = None,
) -> Settings:
    def get_api_key() -> str:
        raise RuntimeError("The api key should already exist")

    return Settings.from_dict(
        fill_missing_settings(
            {
                "hypixel_api_key": hypixel_api_key,
                "antisniper_api_key": antisniper_api_key,
                "use_antisniper_api": use_antisniper_api,
                "known_nicks": known_nicks or {},
            },
            get_api_key,
        )[0],
        path=path or Path("make_settings_settingsfile.json"),
    )


def missing_method(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError


@dataclass
class MockedController:
    """Class implementing the OverlayController protocol for testing"""

    in_queue: bool = False
    api_key_invalid: bool = False
    on_hypixel: bool = True
    hypixel_api_key: str = "api-key"
    antisniper_api_key: str | None = None

    state: OverlayState = field(default_factory=create_state)
    settings: Settings = field(default_factory=make_settings)
    nick_database: NickDatabase = field(default_factory=lambda: NickDatabase([{}]))
    player_cache: PlayerCache = field(
        default_factory=PlayerCache, repr=False, compare=False, hash=False
    )
    redraw_event: threading.Event = field(
        default_factory=threading.Event, repr=False, compare=False, hash=False
    )

    get_uuid: Callable[[str], str | None] = field(
        default=missing_method, repr=False, compare=False, hash=False
    )
    get_player_data: Callable[[str], dict[str, Any] | None] = field(
        default=missing_method, repr=False, compare=False, hash=False
    )
    denick: Callable[[str], str | None] = field(
        default=missing_method, repr=False, compare=False, hash=False
    )
    get_estimated_winstreaks: Callable[[str], tuple[Winstreaks, bool]] = field(
        default=missing_method, repr=False, compare=False, hash=False
    )

    _stored_settings: Settings | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.settings.hypixel_api_key = self.hypixel_api_key
        self.settings.antisniper_api_key = self.antisniper_api_key

    def set_hypixel_api_key(self, new_key: str) -> None:
        self.hypixel_api_key = new_key

    def set_antisniper_api_key(self, new_key: str | None) -> None:
        self.antisniper_api_key = new_key

    def store_settings(self) -> None:
        self._stored_settings = replace(self.settings)
