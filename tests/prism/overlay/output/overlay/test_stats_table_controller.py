import unittest.mock
from typing import cast

from prism.overlay.output.cell_renderer import RenderedStats
from prism.overlay.output.cells import (
    GUI_COLORS,
    CellValue,
    ColumnName,
)
from prism.overlay.output.overlay.stats_table_controller import (
    GUIRow,
    StatsTableController,
    maybe_add_tags_column,
)
from prism.overlay.output.overlay.utils import OverlayRowData

DEFAULT_COLUMNS: tuple[ColumnName, ...] = ("username", "stars", "fkdr")
ALT_COLUMNS: tuple[ColumnName, ...] = ("username", "fkdr", "kdr", "winstreak")


def _make_cell(text: str) -> CellValue:
    return CellValue.monochrome(text, GUI_COLORS[1])


def _make_row(*, key: str, nickname: str | None = None) -> GUIRow:
    """Build a unique GUIRow keyed by `key` for diffing tests."""
    return GUIRow(
        cells=(
            _make_cell(f"{key}-username"),
            _make_cell(f"{key}-stars"),
            _make_cell(f"{key}-fkdr"),
        ),
        nickname=nickname,
    )


def _make_rendered_stats(tags: CellValue) -> RenderedStats:
    cell = _make_cell("x")
    return RenderedStats(
        username=cell,
        stars=cell,
        index=cell,
        fkdr=cell,
        kdr=cell,
        bblr=cell,
        wlr=cell,
        winstreak=cell,
        kills=cell,
        finals=cell,
        beds=cell,
        wins=cell,
        sessiontime=cell,
        tags=tags,
    )


def _make_controller() -> StatsTableController:
    return StatsTableController.create(
        set_column_order=unittest.mock.MagicMock(),
        set_row_count=unittest.mock.MagicMock(),
        set_row=unittest.mock.MagicMock(),
    )


def _set_column_order_mock(c: StatsTableController) -> unittest.mock.MagicMock:
    return cast(unittest.mock.MagicMock, c.set_column_order)


def _set_row_count_mock(c: StatsTableController) -> unittest.mock.MagicMock:
    return cast(unittest.mock.MagicMock, c.set_row_count)


def _set_row_mock(c: StatsTableController) -> unittest.mock.MagicMock:
    return cast(unittest.mock.MagicMock, c.set_row)


def _reset(c: StatsTableController) -> None:
    _set_column_order_mock(c).reset_mock()
    _set_row_count_mock(c).reset_mock()
    _set_row_mock(c).reset_mock()


# ----- StatsTableController -----


def test_first_tick_draws_everything() -> None:
    c = _make_controller()
    rows = (_make_row(key="a"), _make_row(key="b"), _make_row(key="c"))

    c.tick(rows, DEFAULT_COLUMNS)

    _set_column_order_mock(c).assert_called_once_with(DEFAULT_COLUMNS)
    _set_row_count_mock(c).assert_called_once_with(3)
    assert _set_row_mock(c).call_args_list == [
        unittest.mock.call(0, rows[0]),
        unittest.mock.call(1, rows[1]),
        unittest.mock.call(2, rows[2]),
    ]


def test_identical_tick_redraws_nothing() -> None:
    c = _make_controller()
    rows = (_make_row(key="a"), _make_row(key="b"))

    c.tick(rows, DEFAULT_COLUMNS)
    _reset(c)

    c.tick(rows, DEFAULT_COLUMNS)

    _set_column_order_mock(c).assert_not_called()
    _set_row_count_mock(c).assert_not_called()
    _set_row_mock(c).assert_not_called()


def test_one_row_changes_only_that_row_redraws() -> None:
    c = _make_controller()
    row_a = _make_row(key="a")
    row_b_v1 = _make_row(key="b")
    row_c = _make_row(key="c")
    row_b_v2 = _make_row(key="b-changed")

    c.tick((row_a, row_b_v1, row_c), DEFAULT_COLUMNS)
    _reset(c)

    c.tick((row_a, row_b_v2, row_c), DEFAULT_COLUMNS)

    _set_column_order_mock(c).assert_not_called()
    _set_row_count_mock(c).assert_not_called()
    _set_row_mock(c).assert_called_once_with(1, row_b_v2)


def test_row_count_grows_only_new_indices_redraw() -> None:
    c = _make_controller()
    row_a = _make_row(key="a")
    row_b = _make_row(key="b")
    row_c = _make_row(key="c")

    c.tick((row_a, row_b), DEFAULT_COLUMNS)
    _reset(c)

    c.tick((row_a, row_b, row_c), DEFAULT_COLUMNS)

    _set_column_order_mock(c).assert_not_called()
    _set_row_count_mock(c).assert_called_once_with(3)
    _set_row_mock(c).assert_called_once_with(2, row_c)


def test_row_count_shrinks_no_spurious_set_row_calls() -> None:
    c = _make_controller()
    row_a = _make_row(key="a")
    row_b = _make_row(key="b")
    row_c = _make_row(key="c")

    c.tick((row_a, row_b, row_c), DEFAULT_COLUMNS)
    _reset(c)

    c.tick((row_a, row_b), DEFAULT_COLUMNS)

    _set_column_order_mock(c).assert_not_called()
    _set_row_count_mock(c).assert_called_once_with(2)
    _set_row_mock(c).assert_not_called()


def test_column_order_change_redraws_all_rows() -> None:
    c = _make_controller()
    rows = (_make_row(key="a"), _make_row(key="b"), _make_row(key="c"))

    c.tick(rows, DEFAULT_COLUMNS)
    _reset(c)

    # Same row identities, different column order — driver tears down rows
    # in set_column_order, so all rows must be re-emitted.
    c.tick(rows, ALT_COLUMNS)

    _set_column_order_mock(c).assert_called_once_with(ALT_COLUMNS)
    _set_row_count_mock(c).assert_called_once_with(3)
    assert _set_row_mock(c).call_args_list == [
        unittest.mock.call(0, rows[0]),
        unittest.mock.call(1, rows[1]),
        unittest.mock.call(2, rows[2]),
    ]


def test_column_order_change_to_same_value_is_a_noop() -> None:
    c = _make_controller()
    rows = (_make_row(key="a"),)

    c.tick(rows, DEFAULT_COLUMNS)
    _reset(c)

    c.tick(rows, DEFAULT_COLUMNS)

    _set_column_order_mock(c).assert_not_called()
    _set_row_count_mock(c).assert_not_called()
    _set_row_mock(c).assert_not_called()


def test_new_rows_none_is_a_noop() -> None:
    c = _make_controller()

    c.tick(None, DEFAULT_COLUMNS)

    _set_column_order_mock(c).assert_not_called()
    _set_row_count_mock(c).assert_not_called()
    _set_row_mock(c).assert_not_called()


def test_new_rows_none_after_data_does_not_clobber_state() -> None:
    c = _make_controller()
    rows = (_make_row(key="a"), _make_row(key="b"))

    c.tick(rows, DEFAULT_COLUMNS)
    _reset(c)

    c.tick(None, DEFAULT_COLUMNS)
    _set_column_order_mock(c).assert_not_called()
    _set_row_count_mock(c).assert_not_called()
    _set_row_mock(c).assert_not_called()

    # Ticking the same data again is still a no-op — the None tick must not
    # have invalidated the cached state.
    c.tick(rows, DEFAULT_COLUMNS)
    _set_column_order_mock(c).assert_not_called()
    _set_row_count_mock(c).assert_not_called()
    _set_row_mock(c).assert_not_called()


def test_empty_rows_after_populated_shrinks_to_zero() -> None:
    c = _make_controller()
    rows = (_make_row(key="a"), _make_row(key="b"))

    c.tick(rows, DEFAULT_COLUMNS)
    _reset(c)

    c.tick((), DEFAULT_COLUMNS)

    _set_column_order_mock(c).assert_not_called()
    _set_row_count_mock(c).assert_called_once_with(0)
    _set_row_mock(c).assert_not_called()


def test_first_tick_with_zero_rows_still_sends_column_order() -> None:
    c = _make_controller()

    c.tick((), DEFAULT_COLUMNS)

    _set_column_order_mock(c).assert_called_once_with(DEFAULT_COLUMNS)
    # 0 == 0 (initial old_count), so set_row_count not called.
    _set_row_count_mock(c).assert_not_called()
    _set_row_mock(c).assert_not_called()


def test_nickname_change_only_redraws_that_row() -> None:
    c = _make_controller()
    row_a = _make_row(key="a", nickname=None)
    row_b = _make_row(key="b", nickname=None)

    c.tick((row_a, row_b), DEFAULT_COLUMNS)
    _reset(c)

    # Same cells, but row_b becomes nicked — equality is field-based so this
    # counts as a change and only row 1 should redraw.
    row_b_nicked = GUIRow(cells=row_b.cells, nickname="someNick")
    c.tick((row_a, row_b_nicked), DEFAULT_COLUMNS)

    _set_row_mock(c).assert_called_once_with(1, row_b_nicked)


# ----- maybe_add_tags_column -----


def test_maybe_add_tags_column_appends_when_visible_tags_present() -> None:
    visible = CellValue.monochrome("C", "#FF0000")
    rows: tuple[OverlayRowData, ...] = (
        (None, _make_rendered_stats(tags=CellValue.empty())),
        (None, _make_rendered_stats(tags=visible)),
    )

    assert maybe_add_tags_column(DEFAULT_COLUMNS, rows) == DEFAULT_COLUMNS + ("tags",)


def test_maybe_add_tags_column_unchanged_when_no_visible_tags() -> None:
    rows: tuple[OverlayRowData, ...] = (
        (None, _make_rendered_stats(tags=CellValue.empty())),
        (None, _make_rendered_stats(tags=CellValue.pending())),
        (None, _make_rendered_stats(tags=CellValue.error())),
        (None, _make_rendered_stats(tags=CellValue.nicked())),
    )

    assert maybe_add_tags_column(DEFAULT_COLUMNS, rows) == DEFAULT_COLUMNS


def test_maybe_add_tags_column_unchanged_when_already_present() -> None:
    visible = CellValue.monochrome("C", "#FF0000")
    rows: tuple[OverlayRowData, ...] = ((None, _make_rendered_stats(tags=visible)),)
    columns_with_tags = DEFAULT_COLUMNS + ("tags",)

    assert maybe_add_tags_column(columns_with_tags, rows) == columns_with_tags


def test_maybe_add_tags_column_no_rows_unchanged() -> None:
    assert maybe_add_tags_column(DEFAULT_COLUMNS, ()) == DEFAULT_COLUMNS
