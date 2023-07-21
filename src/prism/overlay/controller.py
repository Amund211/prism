import logging
import threading
from abc import abstractmethod
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Protocol

from prism.mojang import MojangAPIError, get_uuid
from prism.overlay.antisniper_api import (
    AntiSniperAPIKeyHolder,
    denick,
    get_antisniper_playerdata,
    get_estimated_winstreaks,
)
from prism.overlay.player import MISSING_WINSTREAKS

if TYPE_CHECKING:  # pragma: no cover
    from prism.overlay.nick_database import NickDatabase
    from prism.overlay.player import Winstreaks
    from prism.overlay.player_cache import PlayerCache
    from prism.overlay.settings import Settings
    from prism.overlay.state import OverlayState

logger = logging.getLogger(__name__)


class OverlayController(Protocol):  # pragma: no cover
    """Class holding components necessary to control the overlay"""

    api_key_invalid: bool
    api_key_throttled: bool
    antisniper_key_holder: AntiSniperAPIKeyHolder

    wants_shown: bool | None
    state: "OverlayState"
    settings: "Settings"
    nick_database: "NickDatabase"
    player_cache: "PlayerCache"
    redraw_event: threading.Event
    update_presence_event: threading.Event

    @property
    @abstractmethod
    def get_uuid(self) -> Callable[[str], str | None]:
        raise NotImplementedError

    @property
    @abstractmethod
    def get_antisniper_playerdata(
        self,
    ) -> Callable[[str], Mapping[str, object] | None]:
        raise NotImplementedError

    @property
    @abstractmethod
    def denick(self) -> Callable[[str], str | None]:
        raise NotImplementedError

    @property
    @abstractmethod
    def get_estimated_winstreaks(self) -> Callable[[str], tuple["Winstreaks", bool]]:
        raise NotImplementedError

    @property
    @abstractmethod
    def store_settings(self) -> Callable[[], None]:
        raise NotImplementedError


class RealOverlayController:
    def __init__(
        self,
        state: "OverlayState",
        settings: "Settings",
        nick_database: "NickDatabase",
    ) -> None:
        from prism.overlay.player_cache import PlayerCache

        self.own_username: str | None = None
        self.api_key_invalid = False
        self.api_key_throttled = False

        self.wants_shown: bool | None = None
        self.player_cache = PlayerCache()
        self.state = state
        self.settings = settings
        self.nick_database = nick_database
        self.redraw_event = threading.Event()
        self.update_presence_event = threading.Event()

        self.antisniper_key_holder = AntiSniperAPIKeyHolder(settings.antisniper_api_key)

    def get_uuid(self, username: str) -> str | None:  # pragma: no cover
        try:
            return get_uuid(username)
        except MojangAPIError as e:
            logger.debug(f"Failed getting uuid for username {username}.", exc_info=e)
            return None

    def get_antisniper_playerdata(
        self, uuid: str
    ) -> Mapping[str, object] | None:  # pragma: no cover
        # TODO: set api key flags
        return get_antisniper_playerdata(uuid, self.antisniper_key_holder)

    def denick(self, nick: str) -> str | None:  # pragma: no cover
        if not self.settings.use_antisniper_api or self.antisniper_key_holder is None:
            return None

        return denick(nick, key_holder=self.antisniper_key_holder)

    def get_estimated_winstreaks(
        self, uuid: str
    ) -> tuple["Winstreaks", bool]:  # pragma: no cover
        if not self.settings.use_antisniper_api or self.antisniper_key_holder is None:
            return MISSING_WINSTREAKS, False

        return get_estimated_winstreaks(uuid, self.antisniper_key_holder)

    def store_settings(self) -> None:
        self.settings.flush_to_disk()
