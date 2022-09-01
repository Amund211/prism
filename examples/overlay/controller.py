from __future__ import annotations

import logging
import threading
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
    from examples.overlay.nick_database import NickDatabase
    from examples.overlay.player import Winstreaks
    from examples.overlay.player_cache import PlayerCache
    from examples.overlay.settings import Settings
    from examples.overlay.state import OverlayState

logger = logging.getLogger(__name__)


class OverlayController(Protocol):  # pragma: no cover
    """Class holding components necessary to control the overlay"""

    in_queue: bool
    api_key_invalid: bool
    on_hypixel: bool

    state: OverlayState
    settings: Settings
    nick_database: NickDatabase
    player_cache: PlayerCache
    redraw_event: threading.Event

    @property
    @abstractmethod
    def set_hypixel_api_key(self) -> Callable[[str], None]:
        raise NotImplementedError

    @property
    @abstractmethod
    def set_antisniper_api_key(self) -> Callable[[str | None], None]:
        raise NotImplementedError

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
        self.redraw_event = threading.Event()

        self.hypixel_key_holder = HypixelAPIKeyHolder(settings.hypixel_api_key)
        self.antisniper_key_holder: AntiSniperAPIKeyHolder | None = None

        self.set_antisniper_api_key(settings.antisniper_api_key)

    def set_hypixel_api_key(self, new_key: str) -> None:
        self.hypixel_key_holder.key = new_key

    def set_antisniper_api_key(self, new_key: str | None) -> None:
        from examples.overlay.antisniper_api import AntiSniperAPIKeyHolder

        current_holder = self.antisniper_key_holder

        if current_holder is None:
            if new_key is None:
                pass
            else:
                self.antisniper_key_holder = AntiSniperAPIKeyHolder(new_key)
        else:
            if new_key is None:
                self.antisniper_key_holder = None
            else:
                current_holder.key = new_key

    def get_uuid(self, username: str) -> str | None:  # pragma: no cover
        try:
            return get_uuid(username)
        except MojangAPIError as e:
            logger.debug(f"Failed getting uuid for username {username} {e=}")
            return None

    def get_player_data(self, uuid: str) -> dict[str, Any] | None:  # pragma: no cover
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

    def denick(self, nick: str) -> str | None:  # pragma: no cover
        if not self.settings.use_antisniper_api or self.antisniper_key_holder is None:
            return None

        from examples.overlay.antisniper_api import denick

        return denick(nick, key_holder=self.antisniper_key_holder)

    def get_estimated_winstreaks(
        self, uuid: str
    ) -> tuple[Winstreaks, bool]:  # pragma: no cover
        from examples.overlay.antisniper_api import get_estimated_winstreaks
        from examples.overlay.player import MISSING_WINSTREAKS

        if not self.settings.use_antisniper_api or self.antisniper_key_holder is None:
            return MISSING_WINSTREAKS, False

        return get_estimated_winstreaks(uuid, self.antisniper_key_holder)

    def store_settings(self) -> None:
        self.settings.flush_to_disk()
