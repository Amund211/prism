import logging
import queue
import sys
import threading
import time
from collections.abc import Iterable

from prism.overlay.behaviour import get_stats_and_winstreak
from prism.overlay.controller import OverlayController
from prism.overlay.keybinds import AlphanumericKey
from prism.overlay.process_event import process_loglines
from prism.overlay.rich_presence import RPCThread
from prism.update_checker import update_available

logger = logging.getLogger(__name__)


class UpdateStateThread(threading.Thread):  # pragma: nocover
    """Thread that reads from the logfile and updates the state"""

    def __init__(self, controller: OverlayController, loglines: Iterable[str]) -> None:
        super().__init__(daemon=True)  # Don't block the process from exiting
        self.controller = controller
        self.loglines = loglines

    def run(self) -> None:
        """Read self.loglines and update self.controller"""
        try:
            process_loglines(self.loglines, self.controller)
        except Exception:
            logger.exception(
                "Exception caught in state update thread. Exiting the overlay."
            )
            # Without state updates the overlay will stop working -> force quit
            sys.exit(1)


class GetStatsThread(threading.Thread):  # pragma: nocover
    """Thread that downloads and stores players' stats to cache"""

    def __init__(
        self,
        requests_queue: queue.Queue[str],
        completed_queue: queue.Queue[str],
        controller: OverlayController,
    ) -> None:
        super().__init__(daemon=True)  # Don't block the process from exiting
        self.requests_queue = requests_queue
        self.completed_queue = completed_queue
        self.controller = controller

    def run(self) -> None:
        """Get requested stats from the queue and download them"""
        try:
            while True:
                username = self.requests_queue.get()

                # Small optimization in case the player left or we switched lobbies
                # between first seeing them and now getting to the request
                # NOTE: We always allow own_username to enable the discord RPC thread
                #       to make requests to compute session stats
                state = self.controller.state
                if username in state.lobby_players or username == state.own_username:
                    get_stats_and_winstreak(
                        username=username,
                        completed_queue=self.completed_queue,
                        controller=self.controller,
                    )
                else:
                    logger.info(f"Skipping get_stats for {username} because they left")
                    # Uncache the pending stats so that if we see them again we will
                    # issue another request, instead of waiting for this one.
                    self.controller.player_cache.uncache_player(username)

                self.requests_queue.task_done()
        except Exception:
            logger.exception("Exception caught in stats thread. Exiting.")
            # Since we spawn multiple stats threads at the start, we can afford some
            # casualties without the overlay completely breaking


class UpdateCheckerThread(threading.Thread):  # pragma: nocover
    """Thread that checks for updates on GitHub once a day"""

    PERIOD_SECONDS = 24 * 60 * 60

    def __init__(
        self,
        one_shot: bool,
        controller: OverlayController,
    ) -> None:
        super().__init__(daemon=True)  # Don't block the process from exiting
        self.one_shot = one_shot
        self.controller = controller

    def run(self) -> None:
        """Run update_available and set the event accordingly"""
        try:
            while True:
                logger.info("UpdateChecker: checking for updates.")
                if not self.controller.settings.check_for_updates:
                    logger.info("UpdateChecker: disabled by settings.")
                elif update_available(
                    ignore_patch_bumps=(
                        not self.controller.settings.include_patch_updates
                    )
                ):
                    logger.info("UpdateChecker: update available!")
                    self.controller.update_available_event.set()
                    # An update is available -> no need to check any more
                    return
                else:
                    logger.info("UpdateChecker: no update available.")

                if self.one_shot:
                    logger.info("UpdateChecker: exiting oneshot thread.")
                    return

                time.sleep(self.PERIOD_SECONDS)
        except Exception:
            logger.exception("Exception caught in update checker thread. Exiting.")


class AutoWhoThread(threading.Thread):  # pragma: nocover
    """Thread that types /who on request, unless cancelled"""

    def __init__(self, controller: OverlayController) -> None:
        super().__init__(daemon=True)  # Don't block the process from exiting
        self.controller = controller

    def run(self) -> None:
        """Wait for requests, check if not cancelled, then type /who"""
        if sys.platform == "darwin":  # Not supported on macOS
            return

        try:
            from pynput.keyboard import Controller, Key, KeyCode

            keyboard = Controller()

            while True:
                # Wait until autowho is requested
                self.controller.autowho_event.wait()

                if not self.controller.settings.autowho:
                    self.controller.autowho_event.clear()
                    continue

                # NOTE: The delay must not be zero!
                # The bedwars game start event is parsed also at the end of a game.
                # We cancel this by parsing a bedwars game end event right after, but
                # need to give a bit of time for the state updater thread to process
                # this event so we don't send /who at the end of a game as well.
                time.sleep(self.controller.settings.autowho_delay)

                if not self.controller.autowho_event.is_set():
                    # Autowho was cancelled
                    continue

                self.controller.autowho_event.clear()

                chat_hotkey = self.controller.settings.chat_hotkey
                chat_keycode: KeyCode
                if isinstance(chat_hotkey, AlphanumericKey):
                    chat_keycode = KeyCode.from_char(chat_hotkey.char)
                elif chat_hotkey.vk is not None:
                    chat_keycode = KeyCode.from_vk(chat_hotkey.vk)
                else:
                    logger.error(f"Invalid chat hotkey {chat_hotkey}")
                    continue

                keyboard.tap(chat_keycode)
                time.sleep(0.1)
                keyboard.type("/who")
                keyboard.tap(Key.enter)
        except Exception:
            logger.exception("Exception caught in autowho thread. Exiting.")
            # We let the overlay keep working if the autowho thread dies


def start_threads(
    controller: OverlayController,
    loglines: Iterable[str],
    requested_stats_queue: queue.Queue[str],
    completed_stats_queue: queue.Queue[str],
) -> None:  # pragma: nocover
    """Spawn threads that perform the state updates and stats downloading"""

    # Spawn thread for updating state
    UpdateStateThread(controller=controller, loglines=loglines).start()

    # Spawn threads for downloading stats
    for i in range(controller.settings.stats_thread_count):
        GetStatsThread(
            requests_queue=requested_stats_queue,
            completed_queue=completed_stats_queue,
            controller=controller,
        ).start()

    RPCThread(
        controller=controller, requested_stats_queue=requested_stats_queue
    ).start()

    AutoWhoThread(controller=controller).start()

    # Spawn thread to check for updates on GitHub
    UpdateCheckerThread(one_shot=False, controller=controller).start()
