import unittest.mock
from typing import cast

from prism.overlay.output.cells import InfoCellValue
from prism.overlay.output.overlay.info_strip_controller import InfoStripController


def _cell(text: str, *, url: str | None = None) -> InfoCellValue:
    return InfoCellValue(text=text, color="snow", url=url)


def _make_controller() -> InfoStripController:
    return InfoStripController.create(
        add_cell=unittest.mock.MagicMock(),
        remove_cell=unittest.mock.MagicMock(),
    )


def _add_mock(c: InfoStripController) -> unittest.mock.MagicMock:
    return cast(unittest.mock.MagicMock, c.add_cell)


def _remove_mock(c: InfoStripController) -> unittest.mock.MagicMock:
    return cast(unittest.mock.MagicMock, c.remove_cell)


def _reset(c: InfoStripController) -> None:
    _add_mock(c).reset_mock()
    _remove_mock(c).reset_mock()


def test_first_tick_adds_all_cells_in_input_order() -> None:
    c = _make_controller()
    a = _cell("a")
    b = _cell("b")
    cc = _cell("c")

    c.tick((a, b, cc))

    assert _add_mock(c).call_args_list == [
        unittest.mock.call(a),
        unittest.mock.call(b),
        unittest.mock.call(cc),
    ]
    _remove_mock(c).assert_not_called()


def test_identical_tick_is_a_noop() -> None:
    c = _make_controller()
    cells = (_cell("a"), _cell("b"))

    c.tick(cells)
    _reset(c)

    c.tick(cells)

    _add_mock(c).assert_not_called()
    _remove_mock(c).assert_not_called()


def test_adding_a_cell_only_adds_that_cell() -> None:
    c = _make_controller()
    a = _cell("a")
    b = _cell("b")
    cc = _cell("c")

    c.tick((a, b))
    _reset(c)

    c.tick((a, b, cc))

    _add_mock(c).assert_called_once_with(cc)
    _remove_mock(c).assert_not_called()


def test_removing_a_cell_only_removes_that_cell() -> None:
    c = _make_controller()
    a = _cell("a")
    b = _cell("b")
    cc = _cell("c")

    c.tick((a, b, cc))
    _reset(c)

    c.tick((a, cc))

    _add_mock(c).assert_not_called()
    _remove_mock(c).assert_called_once_with(b)


def test_add_and_remove_in_same_tick() -> None:
    c = _make_controller()
    a = _cell("a")
    b = _cell("b")
    cc = _cell("c")

    c.tick((a, b))
    _reset(c)

    c.tick((a, cc))

    _add_mock(c).assert_called_once_with(cc)
    _remove_mock(c).assert_called_once_with(b)


def test_clearing_to_empty_removes_everything() -> None:
    c = _make_controller()
    a = _cell("a")
    b = _cell("b")

    c.tick((a, b))
    _reset(c)

    c.tick(())

    _add_mock(c).assert_not_called()
    assert _remove_mock(c).call_args_list == [
        unittest.mock.call(a),
        unittest.mock.call(b),
    ]


def test_first_tick_empty_does_nothing() -> None:
    c = _make_controller()

    c.tick(())

    _add_mock(c).assert_not_called()
    _remove_mock(c).assert_not_called()


def test_duplicates_in_input_added_once() -> None:
    c = _make_controller()
    a = _cell("a")
    b = _cell("b")

    c.tick((a, b, a))

    # The duplicate `a` is collapsed; driver sees each unique cell once.
    assert _add_mock(c).call_args_list == [
        unittest.mock.call(a),
        unittest.mock.call(b),
    ]


def test_duplicates_in_subsequent_tick_remain_a_noop() -> None:
    c = _make_controller()
    a = _cell("a")
    b = _cell("b")

    c.tick((a, b))
    _reset(c)

    # Resending with a duplicate must not re-add an already-present cell.
    c.tick((a, b, a))

    _add_mock(c).assert_not_called()
    _remove_mock(c).assert_not_called()


def test_full_swap_removes_old_then_adds_new() -> None:
    c = _make_controller()
    a = _cell("a")
    b = _cell("b")
    x = _cell("x")
    y = _cell("y")

    c.tick((a, b))
    _reset(c)

    c.tick((x, y))

    assert _remove_mock(c).call_args_list == [
        unittest.mock.call(a),
        unittest.mock.call(b),
    ]
    assert _add_mock(c).call_args_list == [
        unittest.mock.call(x),
        unittest.mock.call(y),
    ]


def test_cells_distinct_by_field_values() -> None:
    """InfoCellValue equality is field-based: same text + color + url == equal."""
    c = _make_controller()
    cell_v1 = _cell("foo")
    cell_v1_again = _cell("foo")  # equal to cell_v1
    cell_v2 = _cell("foo", url="http://example.com")  # different url -> different cell

    c.tick((cell_v1,))
    _reset(c)

    # Same cell, no work
    c.tick((cell_v1_again,))
    _add_mock(c).assert_not_called()
    _remove_mock(c).assert_not_called()

    # Different url => different cell => swap
    c.tick((cell_v2,))
    _remove_mock(c).assert_called_once_with(cell_v1)
    _add_mock(c).assert_called_once_with(cell_v2)
