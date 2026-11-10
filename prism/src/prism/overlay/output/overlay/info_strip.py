import logging
import tkinter as tk
from collections.abc import Callable

from prism.overlay.output.cells import InfoCellValue
from prism.overlay.output.overlay.info_strip_controller import InfoStripController

logger = logging.getLogger(__name__)


class InfoStrip:  # pragma: nocover
    """Standalone info-cell strip driven by an InfoStripController.

    Owns its own frame; tracks a label per visible InfoCellValue. Takes
    `on_link_click` as constructor injection so the widget has no
    dependency on the overlay singleton or `webbrowser`.
    """

    def __init__(
        self,
        parent: tk.Misc,
        on_link_click: Callable[[str], None],
    ) -> None:
        self.on_link_click = on_link_click

        self.frame = tk.Frame(parent, background="black")
        self.frame.pack(side=tk.TOP, expand=True, fill=tk.X)

        self.frame.bind("<Expose>", self._shrink_when_empty)

        self.labels: dict[InfoCellValue, tk.Label] = {}

        self.controller = InfoStripController.create(
            add_cell=self._add_cell,
            remove_cell=self._remove_cell,
        )

    def tick(self, cells: tuple[InfoCellValue, ...]) -> None:
        """Apply one frame of info-strip updates."""
        self.controller.tick(cells)

    # ----- driver methods -----

    def _add_cell(self, cell: InfoCellValue) -> None:
        label = tk.Label(
            self.frame,
            text=cell.text,
            font=("Consolas", 14),
            fg=cell.color,
            bg="black",
        )

        if cell.url is not None:
            label.config(cursor="hand2")
            label.bind("<Button-1>", self._make_link_click_handler(cell.url))

        label.pack(side=tk.TOP)
        self.labels[cell] = label

    def _remove_cell(self, cell: InfoCellValue) -> None:
        label = self.labels.pop(cell)
        label.destroy()

    # ----- internals -----

    def _shrink_when_empty(self, event: "tk.Event[tk.Frame]") -> None:
        """Manually shrink the strip when it becomes empty."""
        if not self.frame.children:
            self.frame.configure(height=1)

    def _make_link_click_handler(
        self, url: str
    ) -> Callable[["tk.Event[tk.Label]"], None]:
        def handler(event: "tk.Event[tk.Label]") -> None:
            self.on_link_click(url)

        return handler
