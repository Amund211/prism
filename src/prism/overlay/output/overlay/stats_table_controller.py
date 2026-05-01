import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Self

from prism.overlay.output.cells import CellValue, ColumnName
from prism.overlay.output.overlay.utils import OverlayRowData

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GUIRow:
    """One row's draw-ready data, post-column-pick.

    `nickname` drives the per-row edit-button state in the driver:
    None disables the button, otherwise the driver wires the click to its
    injected `on_edit_click(nickname)` handler.
    """

    cells: tuple[CellValue, ...]
    nickname: str | None


@dataclass
class StatsTableController:
    """State machine driving stats-table redraws via injected callbacks.

    The driver contract: `set_column_order` is destructive — after it returns,
    the driver has zero rows (because changing columns invalidates per-row
    widgets). The controller honors that by resetting `last_rows` and
    re-issuing `set_row_count` + `set_row` for every row on a column change.
    """

    # Cached previous render — used for diffing
    last_column_order: tuple[ColumnName, ...] | None
    last_rows: tuple[GUIRow, ...] | None

    # Callbacks (the "driver")
    set_column_order: Callable[[tuple[ColumnName, ...]], None]
    set_row_count: Callable[[int], None]
    set_row: Callable[[int, GUIRow], None]

    @classmethod
    def create(
        cls,
        set_column_order: Callable[[tuple[ColumnName, ...]], None],
        set_row_count: Callable[[int], None],
        set_row: Callable[[int, GUIRow], None],
    ) -> Self:
        return cls(
            last_column_order=None,
            last_rows=None,
            set_column_order=set_column_order,
            set_row_count=set_row_count,
            set_row=set_row,
        )

    def tick(
        self,
        new_rows: tuple[GUIRow, ...] | None,
        column_order: tuple[ColumnName, ...],
    ) -> None:
        """Apply one frame of updates to the table.

        If `new_rows is None` (no fresh data this tick) the call is a no-op,
        matching the pre-refactor behavior of `MainContent.update_content`.
        """
        if new_rows is None:
            return

        if column_order != self.last_column_order:
            self.set_column_order(column_order)
            self.last_column_order = column_order
            # set_column_order destroyed all rows in the driver
            self.last_rows = None

        old_count = 0 if self.last_rows is None else len(self.last_rows)
        new_count = len(new_rows)

        if new_count != old_count:
            self.set_row_count(new_count)

        for i, row in enumerate(new_rows):
            old_row = (
                self.last_rows[i]
                if self.last_rows is not None and i < old_count
                else None
            )
            if row != old_row:
                self.set_row(i, row)

        self.last_rows = new_rows


def maybe_add_tags_column(
    column_order: tuple[ColumnName, ...],
    rows: tuple[OverlayRowData, ...],
) -> tuple[ColumnName, ...]:
    """Append 'tags' to column_order if any row has a visible tags cell.

    Mirrors the auto-injection that lived inline in
    `MainContent.update_column_order`. Pending / error / nicked / empty tags
    cells are treated as "no visible tags" and don't trigger the column.
    """
    if "tags" in column_order:
        return column_order

    has_visible_tags = any(
        not row[1].tags.is_pending
        and not row[1].tags.is_error
        and not row[1].tags.is_nicked
        and not row[1].tags.is_empty
        for row in rows
    )

    if has_visible_tags:
        return column_order + ("tags",)
    return column_order
