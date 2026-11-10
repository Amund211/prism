from dataclasses import dataclass

import pytest

from prism.overlay.output.cells import (
    ALL_COLUMN_NAMES,
    COLUMN_NAMES,
    GUI_COLORS,
    CellValue,
)


def test_column_names() -> None:
    assert set(ALL_COLUMN_NAMES) == set(COLUMN_NAMES.keys())


@dataclass(frozen=True, slots=True)
class CellValueIdentities:
    pending: bool = False
    error: bool = False
    nicked: bool = False
    empty: bool = False


@pytest.mark.parametrize(
    "cellvalue, identities",
    (
        (CellValue.pending(), CellValueIdentities(pending=True)),
        (CellValue.error(), CellValueIdentities(error=True)),
        (CellValue.nicked(), CellValueIdentities(nicked=True)),
        (CellValue.empty(), CellValueIdentities(empty=True)),
        (
            # Missing value should not be treated as pending
            CellValue.monochrome("-", GUI_COLORS[-1]),
            CellValueIdentities(),
        ),
        (
            # Manually created pending value should be treated as pending
            CellValue.monochrome("-", GUI_COLORS[0]),
            CellValueIdentities(pending=True),
        ),
    ),
)
def test_cellvalue_identity(
    cellvalue: CellValue, identities: CellValueIdentities
) -> None:
    assert cellvalue.is_pending == identities.pending
    assert cellvalue.is_error == identities.error
    assert cellvalue.is_nicked == identities.nicked
    assert cellvalue.is_empty == identities.empty
