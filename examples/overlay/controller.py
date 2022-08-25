from __future__ import annotations

import logging
from abc import abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol

from prism.minecraft import MojangAPIError, get_uuid
from prism.playerdata import (
    HypixelAPIError,
    HypixelAPIKeyError,
    HypixelAPIKeyHolder,
    get_player_data,
)

if TYPE_CHECKING:  # pragma: no cover
    from examples.overlay.antisniper_api import Winstreaks
    from examples.overlay.nick_database import NickDatabase
    from examples.overlay.player_cache import PlayerCache
    from examples.overlay.settings import Settings
    from examples.overlay.state import OverlayState

logger = logging.getLogger(__name__)


class OverlayController(Protocol):
    """Class holding components necessary to control the overlay"""

    in_queue: bool
    api_key_invalid: bool
    on_hypixel: bool
    hypixel_api_key: str
    antisniper_api_key: str | None

    state: OverlayState
    settings: Settings
    nick_database: NickDatabase
    player_cache: PlayerCache

    @property
    @abstractmethod
    def get_uuid(self) -> Callable[[str], str | None]:
        raise NotImplementedError

    @property
    @abstractmethod
    def get_player_data(self) -> Callable[[str], dict[str, Any] | None]:
        raise NotImplementedError

    @property
    @abstractmethod
    def denick(self) -> Callable[[str], str | None]:
        raise NotImplementedError

    @property
    @abstractmethod
    def get_estimated_winstreaks(self) -> Callable[[str], tuple[Winstreaks, bool]]:
        raise NotImplementedError

    @property
    @abstractmethod
    def store_settings(self) -> Callable[[], None]:
        raise NotImplementedError


class RealOverlayController:
    def __init__(
        self,
        state: OverlayState,
        settings: Settings,
        nick_database: NickDatabase,
    ) -> None:
        from examples.overlay.antisniper_api import AntiSniperAPIKeyHolder
        from examples.overlay.player_cache import PlayerCache

        self.in_queue = False
        self.own_username: str | None = None
        self.api_key_invalid = False
        self.on_hypixel = False

        self.player_cache = PlayerCache()
        self.state = state
        self.settings = settings
        self.nick_database = nick_database

        self.hypixel_key_holder = HypixelAPIKeyHolder("")
        self.hypixel_api_key = settings.hypixel_api_key
        self.antisniper_key_holder: AntiSniperAPIKeyHolder | None = None
        self.antisniper_api_key = settings.antisniper_api_key

    @property
    def hypixel_api_key(self) -> str:
        return self.hypixel_key_holder.key

    @hypixel_api_key.setter
    def hypixel_api_key(self, new_key: str) -> None:
        self.hypixel_key_holder.key = new_key

    @property
    def antisniper_api_key(self) -> str | None:
        current_holder = self.antisniper_key_holder

        if current_holder is None:
            return None

        return current_holder.key

    @antisniper_api_key.setter
    def antisniper_api_key(self, new_key: str | None) -> None:
        from examples.overlay.antisniper_api import AntiSniperAPIKeyHolder

        current_holder = self.antisniper_key_holder

        if current_holder is None:
            if new_key is None or not self.settings.use_antisniper_api:
                pass
            else:
                self.antisniper_key_holder = AntiSniperAPIKeyHolder(new_key)
        else:
            if new_key is None or not self.settings.use_antisniper_api:
                self.antisniper_key_holder = None
            else:
                current_holder.key = new_key

    def get_uuid(self, username: str) -> str | None:
        try:
            return get_uuid(username)
        except MojangAPIError as e:
            logger.debug(f"Failed getting uuid for username {username} {e=}")
            return None

    def get_player_data(self, uuid: str) -> dict[str, Any] | None:
        try:
            player_data = get_player_data(uuid, self.hypixel_key_holder)
        except HypixelAPIError as e:
            logger.debug(f"Failed getting stats for {uuid=} {e=}")
            self.api_key_invalid = False
            return None
        except HypixelAPIKeyError as e:
            logger.debug(f"Invalid API key {e=}")
            self.api_key_invalid = True
            return None
        else:
            self.api_key_invalid = False
            return player_data

    def denick(self, nick: str) -> str | None:
        if self.antisniper_key_holder is None:
            return None

        from examples.overlay.antisniper_api import denick

        return denick(nick, key_holder=self.antisniper_key_holder)

    def get_estimated_winstreaks(self, uuid: str) -> tuple[Winstreaks, bool]:
        from examples.overlay.antisniper_api import (
            MISSING_WINSTREAKS,
            get_estimated_winstreaks,
        )

        if self.antisniper_key_holder is None:
            return MISSING_WINSTREAKS, False

        return get_estimated_winstreaks(uuid, self.antisniper_key_holder)

    def store_settings(self) -> None:
        self.settings.flush_to_disk()
