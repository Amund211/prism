import logging
import tkinter as tk

from prism.overlay.output.cells import CellValue
from prism.overlay.team_types import TeamDangerBannerData

logger = logging.getLogger(__name__)


class RushPopup:  # pragma: nocover
    """
    Dedicated compact HUD pop-up card for the Rush / Target Recommendation.
    Appears automatically on screen after /who calculation completes.
    """

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.window: tk.Toplevel | None = None
        self.is_shown = False
        self.headline_widget: tk.Text | None = None
        self.summary_widget: tk.Text | None = None

    def _ensure_window(self) -> tk.Toplevel:
        if self.window is not None and self.window.winfo_exists():
            return self.window

        window = tk.Toplevel(self.root)
        window.overrideredirect(True)
        window.wm_attributes("-topmost", True)
        window.configure(
            background="#0d0d0d",
            highlightbackground="#FFAA00",
            highlightcolor="#FFAA00",
            highlightthickness=2,
        )

        title_label = tk.Label(
            window,
            text="⚔️ WHO TO RUSH",
            font=("Consolas", 11, "bold"),
            fg="#FFAA00",
            bg="#0d0d0d",
        )
        title_label.pack(side=tk.TOP, pady=(4, 2))

        self.headline_widget = self._create_text_widget(window, font_size=12)
        self.headline_widget.pack(side=tk.TOP, padx=8)

        self.summary_widget = self._create_text_widget(window, font_size=10)
        self.summary_widget.pack(side=tk.TOP, padx=8, pady=(2, 2))

        footnote_label = tk.Label(
            window,
            text="Auto-closing in 10s • Hold Tab for full stats",
            font=("Consolas", 8),
            fg="gray60",
            bg="#0d0d0d",
        )
        footnote_label.pack(side=tk.TOP, pady=(0, 4))

        window.withdraw()
        self.window = window
        return window

    def _create_text_widget(self, parent: tk.Misc, font_size: int) -> tk.Text:
        return tk.Text(
            parent,
            font=("Consolas", font_size),
            fg="gray70",
            bg="#0d0d0d",
            undo=False,
            cursor="arrow",
            height=1,
            wrap="none",
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=0,
        )

    def tick(self, banner: TeamDangerBannerData) -> None:
        """Render banner and ensure popup is visible."""
        window = self._ensure_window()

        if self.headline_widget is not None:
            self._render_line(self.headline_widget, banner.headline)

        if self.summary_widget is not None:
            if banner.team_summary_line is not None:
                self._render_line(
                    self.summary_widget,
                    banner.team_summary_line,
                )
                self.summary_widget.pack(side=tk.TOP, padx=8, pady=(2, 2))
            else:
                self.summary_widget.pack_forget()

        if not self.is_shown:
            window.update_idletasks()
            width = max(window.winfo_reqwidth(), 460)
            height = max(window.winfo_reqheight(), 85)
            screen_w = window.winfo_screenwidth()
            screen_h = window.winfo_screenheight()
            x = (screen_w - width) // 2
            y = max(60, screen_h // 8)
            window.geometry(f"{width}x{height}+{x}+{y}")
            window.deiconify()
            window.lift()
            self.is_shown = True

    def hide(self) -> None:
        """Hide the pop-up window."""
        if self.window is not None and self.window.winfo_exists() and self.is_shown:
            self.window.withdraw()
            self.is_shown = False

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
            tag_end_idx = (
                tk.END
                if color_section.length == -1
                else f"1.0+{tag_start + color_section.length}c"
            )
            text_widget.tag_add(tag_name, f"1.0+{tag_start}c", tag_end_idx)
            text_widget.tag_config(tag_name, foreground=color_section.color)
            if color_section.length != -1:
                tag_start += color_section.length
        text_widget.configure(state=tk.DISABLED)
