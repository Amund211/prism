import logging
import threading
import time
from collections.abc import Mapping
from typing import TYPE_CHECKING

from prism.hypixel import (
    HypixelAPIError,
    HypixelAPIKeyError,
    HypixelAPIThrottleError,
    HypixelPlayerNotFoundError,
)
from prism.mojang import MojangAPIError, get_uuid
from prism.overlay.antisniper_api import (
    AntiSniperAPIKeyHolder,
    get_estimated_winstreaks,
    get_playerdata,
)
from prism.overlay.controller import ERROR_DURING_PROCESSING, ProcessingError
from prism.overlay.player import MISSING_WINSTREAKS
from prism.ratelimiting import RateLimiter
from prism.ssl_errors import MissingLocalIssuerSSLError

if TYPE_CHECKING:  # pragma: no cover
    from prism.overlay.nick_database import NickDatabase
    from prism.overlay.player import Winstreaks
    from prism.overlay.settings import Settings
    from prism.overlay.state import OverlayState

logger = logging.getLogger(__name__)

API_REQUEST_LIMIT = 120
API_REQUEST_WINDOW = 60


class RealOverlayController:
    def __init__(
        self,
        state: "OverlayState",
        settings: "Settings",
        nick_database: "NickDatabase",
    ) -> None:
        from prism.overlay.player_cache import PlayerCache

        self.api_key_invalid = False
        self.api_key_throttled = False
        self.missing_local_issuer_certificate = False
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

        self.antisniper_key_holder: AntiSniperAPIKeyHolder | None = (
            AntiSniperAPIKeyHolder(settings.antisniper_api_key)
            if settings.antisniper_api_key is not None
            else None
        )

    def get_uuid(self, username: str) -> str | None | ProcessingError:
        try:
            uuid = get_uuid(username)
        except MissingLocalIssuerSSLError:
            logger.exception("get_uuid: missing local issuer cert")
            self.missing_local_issuer_certificate = True
            return ERROR_DURING_PROCESSING
        except MojangAPIError as e:
            logger.debug(f"Failed getting uuid for username {username}.", exc_info=e)
            # TODO: RETURN SOMETHING ELSE
            return ERROR_DURING_PROCESSING
        else:
            self.missing_local_issuer_certificate = False
            return uuid

    def get_playerdata(
        self, uuid: str
    ) -> tuple[int, Mapping[str, object] | None | ProcessingError]:
        # TODO: set api key flags
        try:
            playerdata = get_playerdata(
                uuid,
                self.settings.user_id,
                self.antisniper_key_holder,
                self.api_limiter,
            )
        except MissingLocalIssuerSSLError:
            logger.exception("get_playerdata: missing local issuer cert")
            self.missing_local_issuer_certificate = True
            return 0, ERROR_DURING_PROCESSING
        except HypixelPlayerNotFoundError as e:
            logger.debug(f"Player not found on Hypixel: {uuid=}", exc_info=e)
            self.api_key_invalid = False
            self.api_key_throttled = False
            self.missing_local_issuer_certificate = False
            return 0, None
        except HypixelAPIError as e:
            logger.error(f"Hypixel API error getting stats for {uuid=}", exc_info=e)
            return 0, ERROR_DURING_PROCESSING
        except HypixelAPIKeyError as e:
            logger.warning(f"Invalid API key getting stats for {uuid=}", exc_info=e)
            self.api_key_invalid = True
            self.api_key_throttled = False
            self.missing_local_issuer_certificate = False
            return 0, ERROR_DURING_PROCESSING
        except HypixelAPIThrottleError as e:
            logger.warning(f"API key throttled getting stats for {uuid=}", exc_info=e)
            self.api_key_invalid = False
            self.api_key_throttled = True
            self.missing_local_issuer_certificate = False
            return 0, ERROR_DURING_PROCESSING
        else:
            dataReceivedAtMs = time.time_ns() // 1_000_000
            self.api_key_invalid = False
            self.api_key_throttled = False
            self.missing_local_issuer_certificate = False
            return dataReceivedAtMs, playerdata

    def get_estimated_winstreaks(
        self, uuid: str
    ) -> tuple["Winstreaks", bool]:  # pragma: no cover
        if not self.settings.use_antisniper_api or self.antisniper_key_holder is None:
            return MISSING_WINSTREAKS, False

        return get_estimated_winstreaks(uuid, self.antisniper_key_holder)

    def store_settings(self) -> None:
        self.settings.flush_to_disk()
