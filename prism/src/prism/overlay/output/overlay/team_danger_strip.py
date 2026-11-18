import logging
import tkinter as tk

from prism.overlay.output.cells import CellValue
from prism.overlay.output.overlay.team_danger_strip_controller import (
    TeamDangerStripController,
)
from prism.overlay.team_types import TeamDangerBannerData

logger = logging.getLogger(__name__)


class TeamDangerStrip:  # pragma: nocover
    """Standalone team-danger strip driven by TeamDangerStripController.

    Owns its own frame; renders headline and optional team summary line using
    tk.Text widgets styled like StatsTable cells.
    """

    def __init__(self, parent: tk.Misc) -> None:
        self.frame = tk.Frame(parent, background="black")
        self.frame.pack(side=tk.TOP, expand=True, fill=tk.X)

        self.frame.bind("<Expose>", self._shrink_when_empty)

        self.headline_widget: tk.Text | None = None
        self.summary_widget: tk.Text | None = None

        self.controller = TeamDangerStripController.create(
            set_banner=self._set_banner,
        )

    def tick(self, banner: TeamDangerBannerData | None) -> None:
        """Apply one frame of team-danger updates."""
        self.controller.tick(banner)

    # ----- driver methods -----

    def _set_banner(self, banner: TeamDangerBannerData | None) -> None:
        if banner is None:
            self._clear()
            return

        if self.headline_widget is None:
            self.headline_widget = self._create_text_widget()
            self.headline_widget.pack(side=tk.TOP)
        self._render_line(self.headline_widget, banner.headline)

        if banner.team_summary_line is not None:
            if self.summary_widget is None:
                self.summary_widget = self._create_text_widget()
                self.summary_widget.pack(side=tk.TOP)
            self._render_line(self.summary_widget, banner.team_summary_line)
        else:
            if self.summary_widget is not None:
                self.summary_widget.destroy()
                self.summary_widget = None

    def _clear(self) -> None:
        if self.headline_widget is not None:
            self.headline_widget.destroy()
            self.headline_widget = None
        if self.summary_widget is not None:
            self.summary_widget.destroy()
            self.summary_widget = None
        self.frame.configure(height=1)

    def _create_text_widget(self) -> tk.Text:
        return tk.Text(
            self.frame,
            font=("Consolas", 12),
            fg="gray60",
            bg="black",
            undo=False,
            cursor="arrow",
            height=1,
            wrap="none",
            background="black",
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=0,
        )

    def _render_line(self, text_widget: tk.Text, cell_value: CellValue) -> None:
        text = cell_value.text

        text_widget.configure(state=tk.NORMAL)
        text_widget.delete("1.0", tk.END)
        text_widget.insert(tk.END, text)

        for tag in text_widget.tag_names():
            text_widget.tag_delete(tag)

        tag_start = 0
        for i, color_section in enumerate(cell_value.color_sections):
            tag_name = f"tag{i}"
            if color_section.length == -1:
                tag_end_idx = tk.END
            else:
                tag_end = tag_start + color_section.length
                tag_end_idx = f"1.{tag_end}"
            text_widget.tag_add(tag_name, f"1.{tag_start}", tag_end_idx)
            text_widget.tag_config(tag_name, foreground=color_section.color)
            if color_section.length != -1:
                tag_start += color_section.length

        last_color = (
            cell_value.color_sections[-1].color
            if cell_value.color_sections
            else "gray60"
        )
        text_widget.configure(
            fg=last_color,
            state=tk.DISABLED,
            width=len(text),
        )

    def _shrink_when_empty(self, event: "tk.Event[tk.Frame]") -> None:
        """Manually shrink the strip when it becomes empty."""
        if not self.frame.children:
            self.frame.configure(height=1)
