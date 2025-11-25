"""Thread that sends rich presence updates to discord"""

import logging
import threading
import time
from collections.abc import Mapping

from prism import VERSION_STRING
from prism.discordrp import Presence
from prism.overlay.behaviour import get_cached_player_or_enqueue_request
from prism.overlay.controller import OverlayController
from prism.player import KnownPlayer, NickedPlayer, Player

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
        self.username: str | None = None
        self.initial_stats: KnownPlayer | None = None
        self.start_time = int(time.time())
        self.last_presence: Mapping[str, object] | None = None
        self.time_since_game_end = 0

    def connect(self) -> None:
        """
        Try connecting to discord until we succeed

        Sends an initial status after connecting
        """
        while True:
            if not self.controller.settings.discord_rich_presence:
                time.sleep(15)
                continue

            logger.info("Attempting to connect to discord.")

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
            if not self.controller.settings.discord_rich_presence:
                self.set_presence(None, reconnect_on_failure=False)  # Clear activity
                time.sleep(15)
                continue

            new_username = self.controller.state.own_username

            if new_username != self.username and new_username is not None:
                self.track(new_username)
                time.sleep(15)
                continue

            if self.username is None:
                time.sleep(15)
                continue

            # Wait for a game to end
            update_presence = self.controller.game_ended_event.wait(timeout=15)
            self.time_since_game_end += 15

            # Update presence when a game ends
            if not update_presence:
                continue

            self.controller.game_ended_event.clear()
            self.time_since_game_end = 15

            # Wait a bit to let Hypixel update the stats in the API
            time.sleep(5)

            self.update_session_presence()
            time.sleep(15)

    def get_stats(self, username: str) -> KnownPlayer | None:
        """
        Request and wait for the stats of the player

        Return None if self.username != username
        """
        stats: Player | None = None

        # Wait for the stats to become available
        while True:
            # Exit the loop if we are going to change usernames
            new_username = self.controller.state.own_username
            if new_username != username:
                logger.warning(
                    f"Username changed, not getting stats {new_username=} {username=}"
                )
                return None

            stats = get_cached_player_or_enqueue_request(self.controller, username)

            if isinstance(stats, KnownPlayer):
                break

            time.sleep(1)

            if isinstance(stats, NickedPlayer):
                # We can't get our own stats - probably API key error
                # Wait a bit longer
                logger.warning(f"Stats for {username} in rpc thread are nicked")
                time.sleep(14)

        return stats

    def track(self, username: str) -> None:
        logger.info(f"Started tracking {username} in rpc thread")
        self.start_time = int(time.time())
        self.username = username

        self.initial_stats = self.get_stats(self.username)
        if self.initial_stats is None:
            logger.warning("Username changed. Cancelling tracking.")
            return

        self.controller.game_ended_event.clear()
        self.time_since_game_end = 0

        self.update_session_presence()

    def update_session_presence(self) -> None:
        if self.initial_stats is None or self.username is None:
            logger.error(
                f"Missing stats or username {self.initial_stats=} {self.username=}"
            )
            return

        new_stats = self.get_stats(self.username)
        if new_stats is None:
            logger.warning("Username changed. Cancelling session presence update.")
            return

        finals = new_stats.stats.finals - self.initial_stats.stats.finals
        beds = new_stats.stats.beds - self.initial_stats.stats.beds
        wins = new_stats.stats.wins - self.initial_stats.stats.wins

        party_members = sorted(self.controller.state.party_members - {self.username})

        party_members_string = (
            f"With: {', '.join(party_members)}" if party_members else "Not in a party"
        )
        session_stats = f"Finals: {finals}, Beds: {beds}, Wins: {wins}"

        if new_stats.stars < 1100:
            star_icon = "✫"
        elif new_stats.stars < 2100:
            star_icon = "✪"
        elif new_stats.stars < 3100:
            star_icon = "❀"
        else:
            star_icon = "✥"

        if self.controller.settings.discord_show_username:
            status = f"[{int(new_stats.stars)}{star_icon}] {self.username}"
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
