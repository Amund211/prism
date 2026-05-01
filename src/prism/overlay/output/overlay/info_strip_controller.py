import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Self

from prism.overlay.output.cells import InfoCellValue

logger = logging.getLogger(__name__)


@dataclass
class InfoStripController:
    """State machine for the info-cell strip above the stats table.

    Diffs the incoming cell list against the previous render and emits
    per-cell add/remove calls. Iteration is deterministic: removes are
    emitted in last-render order, adds in input order, so tests can
    assert on call sequence.
    """

    last_cells: tuple[InfoCellValue, ...] | None

    add_cell: Callable[[InfoCellValue], None]
    remove_cell: Callable[[InfoCellValue], None]

    @classmethod
    def create(
        cls,
        add_cell: Callable[[InfoCellValue], None],
        remove_cell: Callable[[InfoCellValue], None],
    ) -> Self:
        return cls(
            last_cells=None,
            add_cell=add_cell,
            remove_cell=remove_cell,
        )

    def tick(self, cells: tuple[InfoCellValue, ...]) -> None:
        """Apply one frame of info-strip updates."""
        previous = self.last_cells if self.last_cells is not None else ()
        previous_set = set(previous)
        current_set = set(cells)

        # Remove cells no longer present, in their previous-render order.
        for cell in previous:
            if cell not in current_set:
                self.remove_cell(cell)

        # Add new cells in input order; skip duplicates within `cells` so the
        # driver only sees each unique cell once per tick.
        seen: set[InfoCellValue] = set()
        for cell in cells:
            if cell in seen:
                continue
            seen.add(cell)
            if cell not in previous_set:
                self.add_cell(cell)

        # Cache the deduplicated, input-ordered tuple so subsequent ticks
        # diff against what the driver actually has on screen.
        self.last_cells = tuple(dict.fromkeys(cells))
