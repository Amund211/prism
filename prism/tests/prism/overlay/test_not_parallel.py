from pathlib import Path

import pytest

from prism.overlay.not_parallel import ensure_not_parallel


def test_not_parallel(tmp_path: Path) -> None:
    lock_path = tmp_path / "prism_overlay.lock"
    ensure_not_parallel(lock_path)

    with pytest.raises(SystemExit):
        ensure_not_parallel(lock_path)
