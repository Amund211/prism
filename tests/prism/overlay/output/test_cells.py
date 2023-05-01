from prism.overlay.output.cells import ALL_COLUMN_NAMES, COLUMN_NAMES


def test_column_names() -> None:
    assert set(ALL_COLUMN_NAMES) == set(COLUMN_NAMES.keys())
