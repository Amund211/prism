import logging
import threading
from abc import abstractmethod
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Protocol

from prism.hypixel import (
    HypixelAPIError,
    HypixelAPIKeyError,
    HypixelAPIKeyHolder,
    HypixelAPIThrottleError,
    HypixelPlayerNotFoundError,
    get_player_data,
)
from prism.mojang import MojangAPIError, get_uuid

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
    hypixel_key_holder: HypixelAPIKeyHolder

    wants_shown: bool | None
    state: "OverlayState"
    settings: "Settings"
    nick_database: "NickDatabase"
    player_cache: "PlayerCache"
    redraw_event: threading.Event
    update_presence_event: threading.Event

    @property
    @abstractmethod
    def set_antisniper_api_key(self) -> Callable[[str], None]:
        raise NotImplementedError

    @property
    @abstractmethod
    def get_uuid(self) -> Callable[[str], str | None]:
        raise NotImplementedError

    @property
    @abstractmethod
    def get_player_data(self) -> Callable[[str], Mapping[str, object] | None]:
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
        from prism.overlay.antisniper_api import AntiSniperAPIKeyHolder
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

        self.hypixel_key_holder = HypixelAPIKeyHolder(settings.hypixel_api_key)
        self.antisniper_key_holder = AntiSniperAPIKeyHolder(settings.antisniper_api_key)

        self.set_antisniper_api_key(settings.antisniper_api_key)

    def set_antisniper_api_key(self, new_key: str) -> None:
        self.antisniper_key_holder.key = new_key

    def get_uuid(self, username: str) -> str | None:  # pragma: no cover
        try:
            return get_uuid(username)
        except MojangAPIError as e:
            logger.debug(f"Failed getting uuid for username {username}.", exc_info=e)
            return None

    def get_player_data(
        self, uuid: str
    ) -> Mapping[str, object] | None:  # pragma: no cover
        try:
            player_data = get_player_data(uuid, self.hypixel_key_holder)
        except HypixelPlayerNotFoundError as e:
            logger.debug(f"Player not found on Hypixel: {uuid=}", exc_info=e)
            self.api_key_invalid = False
            self.api_key_throttled = False
            return None
        except HypixelAPIError as e:
            logger.error(f"Hypixel API error getting stats for {uuid=}", exc_info=e)
            return None
        except HypixelAPIKeyError as e:
            logger.warning(f"Invalid API key getting stats for {uuid=}", exc_info=e)
            self.api_key_invalid = True
            self.api_key_throttled = False
            return None
        except HypixelAPIThrottleError as e:
            logger.warning(f"API key throttled getting stats for {uuid=}", exc_info=e)
            self.api_key_invalid = False
            self.api_key_throttled = True
            return None
        else:
            self.api_key_invalid = False
            self.api_key_throttled = False
            return player_data

    def denick(self, nick: str) -> str | None:  # pragma: no cover
        if not self.settings.use_antisniper_api or self.antisniper_key_holder is None:
            return None

        from prism.overlay.antisniper_api import denick

        return denick(nick, key_holder=self.antisniper_key_holder)

    def get_estimated_winstreaks(
        self, uuid: str
    ) -> tuple["Winstreaks", bool]:  # pragma: no cover
        from prism.overlay.antisniper_api import get_estimated_winstreaks
        from prism.overlay.player import MISSING_WINSTREAKS

        if not self.settings.use_antisniper_api or self.antisniper_key_holder is None:
            return MISSING_WINSTREAKS, False

        return get_estimated_winstreaks(uuid, self.antisniper_key_holder)

    def store_settings(self) -> None:
        self.settings.flush_to_disk()
