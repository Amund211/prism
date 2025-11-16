import logging
import threading
from enum import Enum
from typing import TYPE_CHECKING, Protocol

from prism.errors import APIError, APIKeyError, APIThrottleError, PlayerNotFoundError
from prism.player import MISSING_WINSTREAKS, Account, KnownPlayer, Tags, Winstreaks
from prism.ssl_errors import MissingLocalIssuerSSLError

if TYPE_CHECKING:  # pragma: no cover
    from prism.overlay.nick_database import NickDatabase
    from prism.overlay.settings import Settings
    from prism.overlay.state import OverlayState

logger = logging.getLogger(__name__)


class ProcessingError(Enum):
    token = 0


ERROR_DURING_PROCESSING = ProcessingError.token


class AccountProvider(Protocol):
    def get_account_by_username(
        self,
        username: str,
        *,
        user_id: str,
    ) -> Account: ...


class PlayerProvider(Protocol):
    def get_player(
        self,
        uuid: str,
        *,
        user_id: str,
    ) -> KnownPlayer: ...

    @property
    def seconds_until_unblocked(self) -> float: ...


class WinstreakProvider(Protocol):
    def get_estimated_winstreaks_for_uuid(
        self,
        uuid: str,
    ) -> tuple[Winstreaks, bool]: ...

    @property
    def seconds_until_unblocked(self) -> float: ...


class TagsProvider(Protocol):
    def get_tags(
        self,
        uuid: str,
        *,
        user_id: str,
        urchin_api_key: str | None,
    ) -> Tags: ...

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
        tags_provider: TagsProvider,
    ) -> None:
        from prism.overlay.player_cache import PlayerCache

        self.urchin_api_key_invalid = False

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
        self.update_available_event = threading.Event()

        self._account_provider = account_provider
        self._player_provider = player_provider
        self._winstreak_provider = winstreak_provider
        self._tags_provider = tags_provider

    def get_uuid(self, username: str) -> str | None | ProcessingError:
        try:
            account = self._account_provider.get_account_by_username(
                username, user_id=self.settings.user_id
            )
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
            return account.uuid

    def get_player(self, uuid: str) -> KnownPlayer | None | ProcessingError:
        try:
            player = self._player_provider.get_player(
                uuid=uuid,
                user_id=self.settings.user_id,
            )
        except MissingLocalIssuerSSLError:
            logger.exception("get_player: missing local issuer cert")
            self.missing_local_issuer_certificate = True
            return ERROR_DURING_PROCESSING
        except PlayerNotFoundError as e:
            logger.debug(f"Player not found on Hypixel: {uuid=}", exc_info=e)
            self.missing_local_issuer_certificate = False
            return None
        except APIError as e:
            logger.error(f"Hypixel API error getting stats for {uuid=}", exc_info=e)
            return ERROR_DURING_PROCESSING
        # TODO: Remove api key errors once we move to flashlight provider
        except APIKeyError as e:
            logger.warning(f"Invalid API key getting stats for {uuid=}", exc_info=e)
            self.missing_local_issuer_certificate = False
            return ERROR_DURING_PROCESSING
        except APIThrottleError as e:
            logger.warning(f"API key throttled getting stats for {uuid=}", exc_info=e)
            self.missing_local_issuer_certificate = False
            return ERROR_DURING_PROCESSING
        else:
            self.missing_local_issuer_certificate = False
            return player

    def get_estimated_winstreaks(self, uuid: str) -> tuple[Winstreaks, bool]:
        try:
            winstreaks, accurate = (
                self._winstreak_provider.get_estimated_winstreaks_for_uuid(uuid)
            )
        except APIError as e:
            logger.error(f"API error getting winstreaks for {uuid=}", exc_info=e)
            return MISSING_WINSTREAKS, False
        else:
            return winstreaks, accurate

    def get_tags(self, uuid: str) -> Tags | ProcessingError:
        # Don't pass the API key if it's invalid
        urchin_api_key = (
            None if self.urchin_api_key_invalid else self.settings.urchin_api_key
        )

        try:
            tags = self._tags_provider.get_tags(
                uuid=uuid,
                user_id=self.settings.user_id,
                urchin_api_key=urchin_api_key,
            )
        except APIKeyError as e:
            logger.warning(
                f"Invalid Urchin API key getting tags for {uuid=}, "
                f"passed_key={urchin_api_key is not None}",
                exc_info=e,
            )
            # Only mark as invalid if we actually passed a key
            if urchin_api_key is not None:
                self.urchin_api_key_invalid = True
            return ERROR_DURING_PROCESSING
        except APIError as e:
            logger.error(f"Error getting tags for {uuid=}", exc_info=e)
            return ERROR_DURING_PROCESSING
        else:
            # Only clear the invalid flag if we successfully used an API key
            if urchin_api_key is not None:
                self.urchin_api_key_invalid = False
            return tags
