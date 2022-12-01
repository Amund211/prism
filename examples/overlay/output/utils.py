from collections.abc import Sequence
from typing import cast

from examples.overlay.player import PropertyName

COLUMN_NAMES: dict[PropertyName, str] = {
    "rank": "Rank",
    "username": "IGN (Nick)",
    "stars": "Stars",
    "fkdr": "FKDR",
    "wlr": "WLR",
    "winstreak": "WS",
}

STAT_LEVELS: dict[PropertyName, Sequence[float] | None] = {
    "stars": (100, 300, 500, 800),
    "fkdr": (1, 2, 4, 8),
    "wlr": (0.3, 1, 2, 4),
    "winstreak": (5, 15, 30, 50),
    "username": None,
    "rank": None,
}


# The included columns in order
COLUMN_ORDER: Sequence[PropertyName] = cast(
    Sequence[PropertyName], ("rank", "username", "stars", "fkdr", "winstreak", "wlr")
)


assert set(STAT_LEVELS.keys()) == set(COLUMN_NAMES.keys())

assert set(COLUMN_ORDER).issubset(set(COLUMN_NAMES.keys()))


def rate_value(value: float, levels: Sequence[float]) -> int:
    """
    Rate the value according to the provided levels (sorted)

    The rating is the smallest index i in levels that is such that
    value < levels[i]
    Alternatively the largest index i in levels such that
    value >= levels[i + 1]
    NOTE: If value >= levels[j] for all j, the rating will be `len(levels)`
    """
    for rating, level in enumerate(levels):
        if value < level:
            return rating

    # Passed all levels
    return rating + 1
