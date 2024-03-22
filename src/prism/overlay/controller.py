import logging
import threading
from abc import abstractmethod
from collections.abc import Callable, Mapping
from enum import Enum
from typing import TYPE_CHECKING, Protocol

from prism.hypixel import (
    HypixelAPIError,
    HypixelAPIKeyError,
    HypixelAPIThrottleError,
    HypixelPlayerNotFoundError,
)
from prism.mojang import MojangAPIError, get_uuid
from prism.overlay.antisniper_api import (
    AntiSniperAPIKeyHolder,
    get_antisniper_playerdata,
    get_estimated_winstreaks,
)
from prism.overlay.player import MISSING_WINSTREAKS
from prism.ratelimiting import RateLimiter

if TYPE_CHECKING:  # pragma: no cover
    from prism.overlay.nick_database import NickDatabase
    from prism.overlay.player import Winstreaks
    from prism.overlay.player_cache import PlayerCache
    from prism.overlay.settings import Settings
    from prism.overlay.state import OverlayState

logger = logging.getLogger(__name__)

API_REQUEST_LIMIT = 120
API_REQUEST_WINDOW = 60


class ProcessingError(Enum):
    token = 0


ERROR_DURING_PROCESSING = ProcessingError.token


class OverlayController(Protocol):  # pragma: no cover
    """Class holding components necessary to control the overlay"""

    api_key_invalid: bool
    api_key_throttled: bool
    antisniper_key_holder: AntiSniperAPIKeyHolder
    api_limiter: RateLimiter

    wants_shown: bool | None
    state: "OverlayState"
    settings: "Settings"
    nick_database: "NickDatabase"
    player_cache: "PlayerCache"
    redraw_event: threading.Event
    update_presence_event: threading.Event

    @property
    @abstractmethod
    def get_uuid(self) -> Callable[[str], str | None | ProcessingError]:
        raise NotImplementedError

    @property
    @abstractmethod
    def get_antisniper_playerdata(
        self,
    ) -> Callable[[str], Mapping[str, object] | None | ProcessingError]:
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
        self.api_limiter = RateLimiter(
            limit=API_REQUEST_LIMIT, window=API_REQUEST_WINDOW
        )

        self.wants_shown: bool | None = None
        self.player_cache = PlayerCache()
        self.state = state
        self.settings = settings
        self.nick_database = nick_database
        self.redraw_event = threading.Event()
        self.update_presence_event = threading.Event()

        self.antisniper_key_holder = AntiSniperAPIKeyHolder(settings.antisniper_api_key)

    def get_uuid(
        self, username: str
    ) -> str | None | ProcessingError:  # pragma: no cover
        try:
            return get_uuid(username)
        except MojangAPIError as e:
            logger.debug(f"Failed getting uuid for username {username}.", exc_info=e)
            # TODO: RETURN SOMETHING ELSE
            return ERROR_DURING_PROCESSING

    def get_antisniper_playerdata(
        self, uuid: str
    ) -> Mapping[str, object] | None | ProcessingError:  # pragma: no cover
        # TODO: set api key flags
        try:
            playerdata = get_antisniper_playerdata(
                uuid,
                self.settings.user_id,
                self.antisniper_key_holder,
                self.api_limiter,
            )
        except HypixelPlayerNotFoundError as e:
            logger.debug(f"Player not found on Hypixel: {uuid=}", exc_info=e)
            self.api_key_invalid = False
            self.api_key_throttled = False
            return None
        except HypixelAPIError as e:
            logger.error(f"Hypixel API error getting stats for {uuid=}", exc_info=e)
            return ERROR_DURING_PROCESSING
        except HypixelAPIKeyError as e:
            logger.warning(f"Invalid API key getting stats for {uuid=}", exc_info=e)
            self.api_key_invalid = True
            self.api_key_throttled = False
            return ERROR_DURING_PROCESSING
        except HypixelAPIThrottleError as e:
            logger.warning(f"API key throttled getting stats for {uuid=}", exc_info=e)
            self.api_key_invalid = False
            self.api_key_throttled = True
            return ERROR_DURING_PROCESSING
        else:
            self.api_key_invalid = False
            self.api_key_throttled = False
            return playerdata

    def get_estimated_winstreaks(
        self, uuid: str
    ) -> tuple["Winstreaks", bool]:  # pragma: no cover
        if not self.settings.use_antisniper_api or self.antisniper_key_holder is None:
            return MISSING_WINSTREAKS, False

        return get_estimated_winstreaks(uuid, self.antisniper_key_holder)

    def store_settings(self) -> None:
        self.settings.flush_to_disk()
