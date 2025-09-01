import logging
import threading
from collections.abc import Callable, Mapping
from enum import Enum
from typing import TYPE_CHECKING, Protocol

from prism.errors import APIError, APIKeyError, APIThrottleError, PlayerNotFoundError
from prism.overlay.antisniper_api import AntiSniperAPIKeyHolder
from prism.player import MISSING_WINSTREAKS, Winstreaks
from prism.ssl_errors import MissingLocalIssuerSSLError

if TYPE_CHECKING:  # pragma: no cover
    from prism.overlay.nick_database import NickDatabase
    from prism.overlay.settings import Settings
    from prism.overlay.state import OverlayState

logger = logging.getLogger(__name__)

API_REQUEST_LIMIT = 120
API_REQUEST_WINDOW = 60


class ProcessingError(Enum):
    token = 0


ERROR_DURING_PROCESSING = ProcessingError.token


class AccountProvider(Protocol):
    def get_uuid_for_username(self, username: str, /) -> str: ...


class PlayerProvider(Protocol):
    def get_playerdata_for_uuid(
        self,
        uuid: str,
        *,
        user_id: str,
    ) -> Mapping[str, object]: ...

    @property
    def seconds_until_unblocked(self) -> float: ...


class WinstreakProvider(Protocol):
    def get_estimated_winstreaks_for_uuid(
        self,
        uuid: str,
        *,
        antisniper_api_key: str,
    ) -> tuple[Winstreaks, bool]: ...

    @property
    def seconds_until_unblocked(self) -> float: ...


class OverlayController:
    def __init__(
        self,
        state: "OverlayState",
        settings: "Settings",
        nick_database: "NickDatabase",
        account_provider: AccountProvider,
        player_provider: PlayerProvider,
        winstreak_provider: WinstreakProvider,
        get_time_ns: Callable[[], int],
    ) -> None:
        from prism.overlay.player_cache import PlayerCache

        self.api_key_invalid = False
        self.api_key_throttled = False
        self.missing_local_issuer_certificate = False

        self.ready = False
        self.wants_shown: bool | None = None
        self.player_cache = PlayerCache()
        self.state = state
        self.settings = settings
        self.nick_database = nick_database
        self.redraw_event = threading.Event()
        self.update_presence_event = threading.Event()
        self.autowho_event = threading.Event()

        self.antisniper_key_holder: AntiSniperAPIKeyHolder | None = (
            AntiSniperAPIKeyHolder(settings.antisniper_api_key)
            if settings.antisniper_api_key is not None
            else None
        )

        self._account_provider = account_provider
        self._player_provider = player_provider
        self._winstreak_provider = winstreak_provider
        self._get_time_ns = get_time_ns

    def get_uuid(self, username: str) -> str | None | ProcessingError:
        try:
            uuid = self._account_provider.get_uuid_for_username(username)
        except PlayerNotFoundError:
            self.missing_local_issuer_certificate = False
            return None
        except MissingLocalIssuerSSLError:
            logger.exception("get_uuid: missing local issuer cert")
            self.missing_local_issuer_certificate = True
            return ERROR_DURING_PROCESSING
        except APIError:
            logger.exception(f"Failed getting uuid for username {username}.")
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
            playerdata = self._player_provider.get_playerdata_for_uuid(
                uuid=uuid,
                user_id=self.settings.user_id,
            )
        except MissingLocalIssuerSSLError:
            logger.exception("get_playerdata: missing local issuer cert")
            self.missing_local_issuer_certificate = True
            return 0, ERROR_DURING_PROCESSING
        except PlayerNotFoundError as e:
            logger.debug(f"Player not found on Hypixel: {uuid=}", exc_info=e)
            self.api_key_invalid = False
            self.api_key_throttled = False
            self.missing_local_issuer_certificate = False
            return 0, None
        except APIError as e:
            logger.error(f"Hypixel API error getting stats for {uuid=}", exc_info=e)
            return 0, ERROR_DURING_PROCESSING
        except APIKeyError as e:
            logger.warning(f"Invalid API key getting stats for {uuid=}", exc_info=e)
            self.api_key_invalid = True
            self.api_key_throttled = False
            self.missing_local_issuer_certificate = False
            return 0, ERROR_DURING_PROCESSING
        except APIThrottleError as e:
            logger.warning(f"API key throttled getting stats for {uuid=}", exc_info=e)
            self.api_key_invalid = False
            self.api_key_throttled = True
            self.missing_local_issuer_certificate = False
            return 0, ERROR_DURING_PROCESSING
        else:
            dataReceivedAtMs = self._get_time_ns() // 1_000_000
            self.api_key_invalid = False
            self.api_key_throttled = False
            self.missing_local_issuer_certificate = False
            return dataReceivedAtMs, playerdata

    def get_estimated_winstreaks(
        self, uuid: str
    ) -> tuple[Winstreaks, bool]:  # pragma: no cover
        if (
            not self.settings.use_antisniper_api
            or self.settings.antisniper_api_key is None
        ):
            return MISSING_WINSTREAKS, False

        # TODO: The controller should handle errors raised here
        return self._winstreak_provider.get_estimated_winstreaks_for_uuid(
            uuid, antisniper_api_key=self.settings.antisniper_api_key
        )
