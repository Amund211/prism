import logging
import tkinter as tk
from collections.abc import Callable
from typing import TYPE_CHECKING

from prism.overlay.keybinds import Key, SpecialKey, create_pynput_normalizer

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: nocover
    from pynput import keyboard

    from prism.overlay.output.overlay.stats_overlay import StatsOverlay


class ToggleButton:  # pragma: nocover
    DISABLED_CONFIG = {
        "text": "Disabled",
        "bg": "red",
        "activebackground": "orange red",
    }
    ENABLED_CONFIG = {
        # NOTE: The trailing space is intentional to reduce resizing when toggling
        "text": "Enabled ",
        "bg": "lime green",
        "activebackground": "lawn green",
    }

    def __init__(
        self,
        frame: tk.Frame,
        *,
        toggle_callback: Callable[[bool], None] = lambda enabled: None,
        start_enabled: bool = True,
    ) -> None:
        self.toggle_callback = toggle_callback

        self.button = tk.Button(
            frame,
            text="",
            font=("Consolas", "12"),
            foreground="black",
            background="black",
            command=self.toggle,
            relief="flat",
            cursor="hand2",
        )

        # Set the initial state of the button
        # Don't run the toggle callback since the user didn't click the button
        self.set(start_enabled, disable_toggle_callback=True)

    @property
    def enabled(self) -> bool:
        """Return the state of the toggle button"""
        return self.button.config("bg")[-1] == self.ENABLED_CONFIG["bg"]  # type:ignore

    def toggle(self) -> None:
        """Toggle the state of the button"""
        self.set(not self.enabled)

    def set(self, enabled: bool, *, disable_toggle_callback: bool = False) -> None:
        """Set the enabled state of the toggle button"""
        self.button.config(**(self.ENABLED_CONFIG if enabled else self.DISABLED_CONFIG))

        if not disable_toggle_callback:
            self.toggle_callback(self.enabled)


class KeybindSelector(ToggleButton):  # pragma: no coverage
    DISABLED_CONFIG = {
        "bg": "gray",
        "activebackground": "light gray",
    }
    ENABLED_CONFIG = {
        "text": "<Select>",
        "bg": "lawn green",
    }

    def __init__(self, frame: tk.Frame, overlay: "StatsOverlay") -> None:
        super().__init__(frame=frame, toggle_callback=self._on_toggle)

        self.overlay = overlay

        self.key: Key = SpecialKey(name="tab", vk=None)

        self.listener: "keyboard.Listener | None" = None

        self.normalize = create_pynput_normalizer()

        # Default to not selecting
        self.set(False)

    @property
    def selecting(self) -> bool:
        """Return True if the user is currently selecting a new keybind"""
        # In this context, self.enabled is True when the user is selecting a new hotkey
        return self.enabled

    def _on_toggle(self, selecting: bool) -> None:
        # Start/stop the listener
        if selecting:
            self._start_listener()
        else:
            self._stop_listener()
            # Display the current selection when not selecting
            self.button.config(text=self.key.name)

    def _on_press(self, pynput_key: "keyboard.Key | keyboard.KeyCode | None") -> None:
        """Handle keypresses"""
        # Fast path out in case the listener is active when we don't need it
        if self.overlay.current_page != "settings" or not self.selecting:
            return

        key = self.normalize(pynput_key)

        if key is not None:
            self.key = key
            # Got a key -> no longer selecting
            self.toggle()

    def _start_listener(self) -> None:
        try:
            from pynput import keyboard
        except Exception:
            logger.exception("Failed to import pynput")

            # Failed to import -> set not selecting and disable the button
            self.set(False)
            self.button.config(state=tk.DISABLED)
        else:
            if self.listener is None:
                self.listener = keyboard.Listener(on_press=self._on_press)
                self.listener.start()

    def _stop_listener(self) -> None:
        if self.listener is not None:
            self.listener.stop()
            self.listener = None

    def set_key(self, key: Key) -> None:
        self.key = key
        self._on_toggle(self.selecting)
