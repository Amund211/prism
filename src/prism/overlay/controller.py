import threading
from abc import abstractmethod
from collections.abc import Callable, Mapping
from enum import Enum
from typing import TYPE_CHECKING, Protocol

from prism.player import Winstreaks

if TYPE_CHECKING:  # pragma: no cover
    from prism.overlay.antisniper_api import AntiSniperAPIKeyHolder
    from prism.overlay.nick_database import NickDatabase
    from prism.overlay.player_cache import PlayerCache
    from prism.overlay.settings import Settings
    from prism.overlay.state import OverlayState
    from prism.ratelimiting import RateLimiter


class ProcessingError(Enum):
    token = 0


ERROR_DURING_PROCESSING = ProcessingError.token


class OverlayController(Protocol):  # pragma: no cover
    """Class holding components necessary to control the overlay"""

    api_key_invalid: bool
    api_key_throttled: bool
    missing_local_issuer_certificate: bool
    antisniper_key_holder: "AntiSniperAPIKeyHolder | None"
    api_limiter: "RateLimiter"

    wants_shown: bool | None
    ready: bool
    state: "OverlayState"
    settings: "Settings"
    nick_database: "NickDatabase"
    player_cache: "PlayerCache"
    autowho_event: threading.Event
    redraw_event: threading.Event
    update_presence_event: threading.Event

    @property
    @abstractmethod
    def get_uuid(self) -> Callable[[str], str | None | ProcessingError]:
        raise NotImplementedError

    @property
    @abstractmethod
    def get_playerdata(
        self,
    ) -> Callable[[str], tuple[int, Mapping[str, object] | None | ProcessingError]]:
        raise NotImplementedError

    @property
    @abstractmethod
    def get_estimated_winstreaks(self) -> Callable[[str], tuple[Winstreaks, bool]]:
        raise NotImplementedError

    @property
    @abstractmethod
    def store_settings(self) -> Callable[[], None]:
        raise NotImplementedError
