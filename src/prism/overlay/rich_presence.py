"""Thread that sends rich presence updates to discord"""

import logging
import queue
import threading
import time
from collections.abc import Mapping

from prism import VERSION_STRING
from prism.discordrp import Presence
from prism.overlay.controller import OverlayController
from prism.player import KnownPlayer

CLIENT_ID = "1102365189845823569"

logger = logging.getLogger(__name__)

BUTTONS = [
    {
        "label": "Download",
        "url": "https://github.com/Amund211/prism",
    },
    {
        "label": "Join the Discord!",
        "url": "https://discord.gg/k4FGUnEHYg",
    },
]

BASE_ASSETS = {
    "large_image": "prism_logo",
    "large_text": f"Prism Overlay {VERSION_STRING}",
    "small_image": "bedwars_icon",
}


class RPCThread(threading.Thread):  # pragma: no coverage
    """Thread that updates discord rich presence after every game"""

    def __init__(self, controller: OverlayController) -> None:
        super().__init__(daemon=True)  # Don't block the process from exiting
        self.controller = controller
        self.initial_player: KnownPlayer | None = None
        self.current_player: KnownPlayer | None = None
        self.start_time = int(time.time())
        self.last_presence: Mapping[str, object] | None = None

        self.previous_presence_settings = self.presence_settings

    @property
    def presence_settings(self) -> tuple[bool, bool, bool, bool]:
        return (
            self.controller.settings.discord_rich_presence,
            self.controller.settings.discord_show_username,
            self.controller.settings.discord_show_session_stats,
            self.controller.settings.discord_show_party,
        )

    def update_settings(self) -> bool:
        """Update presence if settings have changed. Return True if so"""
        previous_settings, current_settings = (
            self.previous_presence_settings,
            self.presence_settings,
        )
        self.previous_presence_settings = current_settings

        return previous_settings != current_settings

    def connect(self) -> None:
        """
        Try connecting to discord until we succeed

        Sends an initial status after connecting
        """
        while True:
            if not self.controller.settings.discord_rich_presence:
                time.sleep(15)
                continue

            logger.debug("Attempting to connect to discord.")

            try:
                # TODO: Proper cleanup of the connection
                self.presence = Presence(CLIENT_ID)
            except Exception:
                logger.debug("Failed connecting to discord", exc_info=True)
                time.sleep(15)
            else:
                break

        logger.info("Connected to discord!")

        self.last_presence = None

        data = {
            "state": "Launching Minecraft",
            "timestamps": {"start": self.start_time},
            "assets": BASE_ASSETS,
            "buttons": BUTTONS,
        }
        # Presence priority is first come, first served, so we send a status
        # as early as possible to claim the spot.
        if self.controller.state.own_username is None:
            self.set_presence(data, reconnect_on_failure=False)
            time.sleep(15)

    def run(self) -> None:
        """Update discord rich presence after every game or every 5 minutes"""
        self.connect()

        while True:
            new_player = None
            try:
                new_player = self.controller.current_player_updates_queue.get(
                    timeout=15
                )
            except queue.Empty:
                # No updates. Continue with current_player = None
                pass

            if not self.controller.settings.discord_rich_presence:
                self.set_presence(None, reconnect_on_failure=False)  # Clear activity
                continue

            if new_player is None:
                # No updates

                if self.update_settings() and self.current_player is not None:
                    # Settings changed - update presence
                    self.update_session_presence(self.current_player)

                continue

            if (
                self.initial_player is None
                or self.initial_player.username.lower() != new_player.username.lower()
            ):
                # We're switching to a new account
                # (either from "no account" or from another account)
                # Start tracking!
                logger.info(f"Started tracking {new_player.username} in rpc thread")
                self.start_time = int(time.time())
                self.initial_player = new_player

            self.current_player = new_player
            # Update the presence with the new player
            self.update_session_presence(new_player)
            time.sleep(15)

    def update_session_presence(self, player: KnownPlayer) -> None:
        if self.initial_player is None:
            logger.error(f"Missing initial stats {self.initial_player=}")
            return

        finals = player.stats.finals - self.initial_player.stats.finals
        beds = player.stats.beds - self.initial_player.stats.beds
        wins = player.stats.wins - self.initial_player.stats.wins

        party_members = sorted(self.controller.state.party_members - {player.username})

        party_members_string = (
            f"With: {', '.join(party_members)}" if party_members else "Not in a party"
        )
        session_stats = f"Finals: {finals}, Beds: {beds}, Wins: {wins}"

        if player.stars < 1100:
            star_icon = "✫"
        elif player.stars < 2100:
            star_icon = "✪"
        elif player.stars < 3100:
            star_icon = "❀"
        else:
            star_icon = "✥"

        if self.controller.settings.discord_show_username:
            status = f"[{int(player.stars)}{star_icon}] {player.username}"
        else:
            status = "Playing Bedwars"

        data = {
            "state": session_stats[:128],
            "details": status[:128],
            "timestamps": {"start": self.start_time},
            "assets": {
                **BASE_ASSETS,
                "small_text": party_members_string[:128],
            },
            "buttons": BUTTONS,
        }
        if not self.controller.settings.discord_show_party:
            del data["assets"]["small_text"]  # type: ignore [attr-defined]
        if not self.controller.settings.discord_show_session_stats:
            del data["state"]

        self.set_presence(data)

    def set_presence(
        self, data: Mapping[str, object] | None, *, reconnect_on_failure: bool = True
    ) -> None:
        if self.last_presence is None and data is None:
            # Don't do repeated clears
            # If we are passed an actual activity we still set it in case
            # discord was restarted since the last time we set the activity.
            return

        self.last_presence = data

        logger.debug(f"Setting presence data {reconnect_on_failure=} {data}")

        try:
            self.presence.set(data)
        except Exception:
            logger.debug("Failed to set presence!", exc_info=True)
            if reconnect_on_failure:
                self.connect()
                self.set_presence(data, reconnect_on_failure=False)
