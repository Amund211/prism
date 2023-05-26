import functools
import logging
import platform
import tkinter as tk
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from prism.overlay.keybinds import Key, SpecialKey, create_pynput_normalizer

SYSTEM = platform.system()

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
        enabled_config: dict[str, Any] = {},
        disabled_config: dict[str, Any] = {},
        start_enabled: bool = True,
    ) -> None:
        self.toggle_callback = toggle_callback

        self.enabled_config = {**self.__class__.ENABLED_CONFIG, **enabled_config}
        self.disabled_config = {**self.__class__.DISABLED_CONFIG, **disabled_config}

        assert self.enabled_config["bg"] != self.disabled_config["bg"]

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
        return self.button.config("bg")[-1] == self.enabled_config["bg"]  # type:ignore

    def toggle(self) -> None:
        """Toggle the state of the button"""
        self.set(not self.enabled)

    def set(self, enabled: bool, *, disable_toggle_callback: bool = False) -> None:
        """Set the enabled state of the toggle button"""
        self.button.config(**(self.enabled_config if enabled else self.disabled_config))

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


class ScrollableFrame:  # pragma: no coverage
    """
    Scrollable tkinter frame

    Based on: https://blog.teclado.com/tkinter-scrollable-frames/
    and: https://stackoverflow.com/questions/73165441/make-the-scrollbar-automatically-scroll-back-up-in-tkinter
    """  # noqa: E501

    def __init__(self, parent: tk.Frame, max_height: int):
        self.container_frame = tk.Frame(parent)
        self.max_height = max_height
        self.scrollbar_shown = False

        # Create canvas and scrollbar
        self.canvas = tk.Canvas(self.container_frame, bg="black", highlightthickness=0)
        self.scrollbar = tk.Scrollbar(
            self.container_frame,
            orient=tk.VERTICAL,
            command=self.canvas.yview,
            bg="black",
            activebackground="dark gray",
            troughcolor="#333333",
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Create content frame and insert it into the canvas
        self.content_frame = tk.Frame(self.canvas, background="black")
        self.content_frame.bind("<Configure>", lambda e: self._update_content_size())
        self.canvas.create_window((0, 0), window=self.content_frame, anchor=tk.NW)
        self.register_scrollarea(self.content_frame)

        self._update_content_size()

    def _update_content_size(self) -> None:
        """Update the scrollregion and width+height for the canvas"""
        content_height = self.content_frame.winfo_height()

        if content_height > self.max_height:
            height = self.max_height
            self._show_scrollbar()
        else:
            height = content_height
            self._hide_scrollbar()

        self.canvas.configure(
            scrollregion=self.canvas.bbox("all"),
            width=self.content_frame.winfo_width(),
            height=height,
        )

    def _show_scrollbar(self) -> None:
        """Show the scrollbar"""
        if not self.scrollbar_shown:
            self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            self.scrollbar_shown = True

    def _hide_scrollbar(self) -> None:
        """Hide the scrollbar"""
        if self.scrollbar_shown:
            self.scrollbar.pack_forget()
            self.scrollbar_shown = False

    def _on_mousewheel(self, event: "tk.Event[tk.Misc]") -> None:
        """Mousewheel callback to scroll the canvas"""
        if SYSTEM == "Windows":
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        else:
            if event.num == 4:
                self.canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                self.canvas.yview_scroll(1, "units")

    def register_scrollarea(self, widget: tk.Widget) -> None:
        """Register a widget to scroll the canvas"""
        if SYSTEM == "Linux":
            widget.bind("<Button-4>", self._on_mousewheel)
            widget.bind("<Button-5>", self._on_mousewheel)
        else:
            widget.bind("<MouseWheel>", self._on_mousewheel)

    def scroll_to_top(self) -> None:
        """Scroll the content to the top"""
        self.canvas.yview_moveto(0)


class OrderedMultiSelect:  # pragma: no coverage
    """Make an ordered selection of multiple items"""

    def __init__(
        self, parent: tk.Frame, items: tuple[str, ...], *, reset_items: tuple[str, ...]
    ) -> None:
        self.frame = tk.Frame(parent, bg="black")

        self.picked_up_index: int | None = None
        self.items = items

        self.listbox = tk.Listbox(
            self.frame,
            activestyle=tk.NONE,
            height=len(items),
            bg="black",
            fg="white",
            cursor="hand2",
        )
        self.listbox.pack(side=tk.LEFT)

        self.listbox.bind("<ButtonPress-1>", self._pick_up_item)
        self.listbox.bind("<B1-Motion>", self._move_item)
        self.listbox.bind("<ButtonRelease-1>", self._drop_item)

        self.toggle_frame = tk.Frame(self.frame, bg="black")
        self.toggle_frame.pack(side=tk.RIGHT)

        assert items, "Items tuple cannot be empty!"

        self.toggles: dict[str, ToggleButton] = {}
        row_length = 3
        row = 0
        while items:
            chunk, items = items[:row_length], items[row_length:]

            for column, item in enumerate(chunk):
                toggle = ToggleButton(
                    self.toggle_frame,
                    toggle_callback=functools.partial(self._toggle_item, item=item),
                    enabled_config={"text": item},
                    disabled_config={"text": item},
                )
                toggle.button.grid(row=row, column=column)
                self.toggles[item] = toggle

            row += 1

        self.reset_button = tk.Button(
            self.toggle_frame,
            text="Reset",
            font=("Consolas", "14"),
            foreground="white",
            background="black",
            command=functools.partial(self.set_selection, reset_items),
            relief="flat",
            cursor="hand2",
        )
        self.reset_button.grid(row=row, column=1)

    def _nearest(self, y: int) -> int:
        """Wrapper for self.listbox.nearest"""
        # Typeshed currently leaves this method untyped
        return self.listbox.nearest(y)  # type: ignore [no-any-return, no-untyped-call]

    def _toggle_item(self, enabled: bool, item: str) -> None:
        """Toggles the item's presence in the selection (listbox)"""
        i: int | None

        for i, current_item in enumerate(self.listbox.get(0, tk.END)):
            if current_item == item:
                break
        else:  # Found no matching item in the list
            i = None

        if enabled:  # Add the item
            if i is not None:
                # The item is already present
                logger.error(f"Tried adding already present {item} to listbox!")
                return
            self.listbox.insert(tk.END, item)
        else:  # Remove the item
            if i is None:
                # The item is not present
                logger.error(f"Tried removing missing {item} from listbox!")
                return
            self.listbox.delete(i)

    def _pick_up_item(self, event: "tk.Event[tk.Listbox]") -> None:
        """Pick up the list item under the cursor"""
        self.picked_up_index = self._nearest(event.y)

    def _drop_item(self, event: "tk.Event[tk.Listbox]") -> None:
        """Drop the currently picked up item"""
        self.picked_up_index = None

    def _move_item(self, event: "tk.Event[tk.Listbox]") -> None:
        """Move the picked up item to the current cursor position"""
        if self.picked_up_index is None:
            return

        new_index = self._nearest(event.y)

        if self.picked_up_index == new_index:
            return

        picked_up_item = self.listbox.get(self.picked_up_index)
        self.listbox.delete(self.picked_up_index)
        self.listbox.insert(new_index, picked_up_item)
        self.picked_up_index = new_index

    def set_selection(self, selection: tuple[str, ...]) -> None:
        """Set the current selection in the listbox"""
        # Update the listbox
        self.listbox.delete(0, tk.END)
        for item in selection:
            self.listbox.insert(tk.END, item)

        # Update the toggles
        for item, toggle in self.toggles.items():
            toggle.set(item in selection, disable_toggle_callback=True)

    def get_selection(self) -> tuple[str, ...]:
        """Get the current selection in the listbox"""
        return tuple(self.listbox.get(0, tk.END))
