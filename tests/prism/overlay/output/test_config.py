from collections.abc import Callable, Mapping

import pytest

from prism.overlay.output.config import (
    RatingConfig,
    RatingConfigCollection,
    RatingConfigCollectionDict,
    RatingConfigDict,
    read_rating_config_collection_dict,
    read_rating_config_dict,
    safe_read_rating_config_collection_dict,
    safe_read_rating_config_dict,
)
from tests.prism.overlay.utils import (
    CUSTOM_RATING_CONFIG_COLLECTION,
    CUSTOM_RATING_CONFIG_COLLECTION_DICT,
    DEFAULT_RATING_CONFIG_COLLECTION,
    DEFAULT_RATING_CONFIG_COLLECTION_DICT,
)


def test_rating_config_input_validation() -> None:
    with pytest.raises(ValueError):
        for decimals in range(1, 10):
            RatingConfig(True, (1.0, 2.0), -decimals, True)

    for decimals in range(10):
        RatingConfig(True, (1.0, 2.0), decimals, True)


@pytest.mark.parametrize(
    "collection_dict, collection",
    (
        (CUSTOM_RATING_CONFIG_COLLECTION_DICT, CUSTOM_RATING_CONFIG_COLLECTION),
        (DEFAULT_RATING_CONFIG_COLLECTION_DICT, DEFAULT_RATING_CONFIG_COLLECTION),
    ),
)
def test_rating_config_collection_serialization(
    collection_dict: RatingConfigCollectionDict, collection: RatingConfigCollection
) -> None:
    assert collection.to_dict() == collection_dict
    assert RatingConfigCollection.from_dict(collection_dict) == collection


READ_RATING_CONFIG_COLLECTION_CASES: tuple[
    tuple[
        Mapping[str, object] | RatingConfigCollectionDict, RatingConfigCollectionDict
    ],
    ...,
] = (
    ({}, DEFAULT_RATING_CONFIG_COLLECTION_DICT),
    (DEFAULT_RATING_CONFIG_COLLECTION_DICT, DEFAULT_RATING_CONFIG_COLLECTION_DICT),
    (CUSTOM_RATING_CONFIG_COLLECTION_DICT, CUSTOM_RATING_CONFIG_COLLECTION_DICT),
    ({"sdlfk": 2349}, DEFAULT_RATING_CONFIG_COLLECTION_DICT),
    ({"stars": 2349}, DEFAULT_RATING_CONFIG_COLLECTION_DICT),
    ({"stars": {"type": "notreal"}}, DEFAULT_RATING_CONFIG_COLLECTION_DICT),
    ({"stars": {"type": "level_based"}}, DEFAULT_RATING_CONFIG_COLLECTION_DICT),
    (
        {"stars": {"type": "level_based", "levels": 1234}},
        DEFAULT_RATING_CONFIG_COLLECTION_DICT,
    ),
    (
        {"stars": {"type": "level_based", "decimals": -1}},
        DEFAULT_RATING_CONFIG_COLLECTION_DICT,
    ),
    (
        dict(DEFAULT_RATING_CONFIG_COLLECTION_DICT, stars=1234),
        DEFAULT_RATING_CONFIG_COLLECTION_DICT,
    ),
    (
        dict(DEFAULT_RATING_CONFIG_COLLECTION_DICT, wlr=1234),
        DEFAULT_RATING_CONFIG_COLLECTION_DICT,
    ),
    (
        dict(DEFAULT_RATING_CONFIG_COLLECTION_DICT, wins=1234),
        DEFAULT_RATING_CONFIG_COLLECTION_DICT,
    ),
)


@pytest.mark.parametrize("source, target", READ_RATING_CONFIG_COLLECTION_CASES)
@pytest.mark.parametrize(
    "reader",
    (read_rating_config_collection_dict, safe_read_rating_config_collection_dict),
)
def test_read_rating_config_collection_dict(
    source: Mapping[str, object],
    target: RatingConfigCollectionDict,
    reader: Callable[[Mapping[str, object]], tuple[RatingConfigCollectionDict, bool]],
) -> None:
    result, source_updated = reader(source)
    assert result == target
    assert source_updated == (source != target)


DEFAULT_LEVELS = (1.0, 2.0, 3.0, 4.0)
DEFAULT_DECIMALS = 2
DEFAULT_RATE_BY_LEVEL = True
DEFAULT_SORT_ASCENDING = True
DEFAULT_CONFIG = RatingConfig(
    rate_by_level=DEFAULT_RATE_BY_LEVEL,
    levels=DEFAULT_LEVELS,
    decimals=DEFAULT_DECIMALS,
    sort_ascending=DEFAULT_SORT_ASCENDING,
)


READ_RATING_CONFIG_CASES: tuple[tuple[Mapping[str, object], RatingConfigDict], ...] = (
    (
        {
            "type": "level_based",
            "rate_by_level": False,
            "levels": (1.0, 5.0),
            "decimals": 4,
            "sort_ascending": False,
        },
        {
            "type": "level_based",
            "rate_by_level": False,
            "levels": (1.0, 5.0),
            "decimals": 4,
            "sort_ascending": False,
        },
    ),
    # type is optional for the time being
    (
        {
            "levels": (1.0, 5.0),
            "rate_by_level": True,
            "decimals": 4,
            "sort_ascending": True,
        },
        {
            "type": "level_based",
            "rate_by_level": True,
            "levels": (1.0, 5.0),
            "decimals": 4,
            "sort_ascending": True,
        },
    ),
    (
        {"levels": (1.0, 5.0)},
        {
            "type": "level_based",
            "rate_by_level": DEFAULT_RATE_BY_LEVEL,
            "levels": (1.0, 5.0),
            "decimals": DEFAULT_DECIMALS,
            "sort_ascending": DEFAULT_SORT_ASCENDING,
        },
    ),
    (
        {"decimals": 10},
        {
            "type": "level_based",
            "rate_by_level": DEFAULT_RATE_BY_LEVEL,
            "levels": DEFAULT_LEVELS,
            "decimals": 10,
            "sort_ascending": DEFAULT_SORT_ASCENDING,
        },
    ),
    (
        {"rate_by_level": False},
        {
            "type": "level_based",
            "rate_by_level": False,
            "levels": DEFAULT_LEVELS,
            "decimals": DEFAULT_DECIMALS,
            "sort_ascending": DEFAULT_SORT_ASCENDING,
        },
    ),
    (
        {"sort_ascending": False},
        {
            "type": "level_based",
            "rate_by_level": DEFAULT_RATE_BY_LEVEL,
            "levels": DEFAULT_LEVELS,
            "decimals": DEFAULT_DECIMALS,
            "sort_ascending": False,
        },
    ),
    (
        {},
        {
            "type": "level_based",
            "rate_by_level": DEFAULT_RATE_BY_LEVEL,
            "levels": DEFAULT_LEVELS,
            "decimals": DEFAULT_DECIMALS,
            "sort_ascending": DEFAULT_SORT_ASCENDING,
        },
    ),
    # ints not accepted
    (
        {"levels": (1, 5)},
        {
            "type": "level_based",
            "rate_by_level": DEFAULT_RATE_BY_LEVEL,
            "levels": DEFAULT_LEVELS,
            "decimals": DEFAULT_DECIMALS,
            "sort_ascending": DEFAULT_SORT_ASCENDING,
        },
    ),
    # Invalid type
    (
        {"levels": 1},
        {
            "type": "level_based",
            "rate_by_level": DEFAULT_RATE_BY_LEVEL,
            "levels": DEFAULT_LEVELS,
            "decimals": DEFAULT_DECIMALS,
            "sort_ascending": DEFAULT_SORT_ASCENDING,
        },
    ),
    # Invalid type
    (
        {"sort_ascending": ""},
        {
            "type": "level_based",
            "rate_by_level": DEFAULT_RATE_BY_LEVEL,
            "levels": DEFAULT_LEVELS,
            "decimals": DEFAULT_DECIMALS,
            "sort_ascending": DEFAULT_SORT_ASCENDING,
        },
    ),
    # Invalid type
    (
        {"decimals": ""},
        {
            "type": "level_based",
            "rate_by_level": DEFAULT_RATE_BY_LEVEL,
            "levels": DEFAULT_LEVELS,
            "decimals": DEFAULT_DECIMALS,
            "sort_ascending": DEFAULT_SORT_ASCENDING,
        },
    ),
    # Invalid value
    (
        {"decimals": -10},
        {
            "type": "level_based",
            "rate_by_level": DEFAULT_RATE_BY_LEVEL,
            "levels": DEFAULT_LEVELS,
            "decimals": DEFAULT_DECIMALS,
            "sort_ascending": DEFAULT_SORT_ASCENDING,
        },
    ),
)


@pytest.mark.parametrize("source, target", READ_RATING_CONFIG_CASES)
@pytest.mark.parametrize(
    "reader",
    (read_rating_config_dict, safe_read_rating_config_dict),
)
def test_read_rating_config_dict(
    source: Mapping[str, object],
    target: RatingConfigDict,
    reader: Callable[
        [Mapping[str, object], RatingConfig],
        tuple[RatingConfigDict, bool],
    ],
) -> None:
    result, source_updated = reader(source, DEFAULT_CONFIG)
    assert result == target
    assert source_updated == (source != target)
