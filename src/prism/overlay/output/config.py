from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, Self, TypedDict

STARS_LEVELS = (100.0, 300.0, 500.0, 800.0)
FKDR_LEVELS = (1.0, 2.0, 4.0, 8.0)
WLR_LEVELS = (0.3, 1.0, 2.0, 4.0)
WINSTREAK_LEVELS = (5.0, 15.0, 30.0, 50.0)


class RatingConfigDict(TypedDict):
    """Dict representing a RatingConfig"""

    type: Literal["level_based"]
    levels: tuple[float, ...]
    decimals: int


def read_rating_config_dict(
    source: Mapping[str, Any], default_levels: tuple[float, ...], default_decimals: int
) -> tuple[RatingConfigDict, bool]:
    """Read a RatingConfigDict from the source mapping"""
    source_updated = False

    if source.get("type", None) != "level_based":
        source_updated = True

    levels = source.get("levels", None)
    if not isinstance(levels, (list, tuple)) or not all(
        isinstance(el, float) for el in levels
    ):
        levels = default_levels
        source_updated = True

    decimals = source.get("decimals", None)
    if not isinstance(decimals, int) or decimals < 0:
        decimals = default_decimals
        source_updated = True

    return {
        "type": "level_based",
        "levels": tuple(levels),
        "decimals": decimals,
    }, source_updated


def safe_read_rating_config_dict(
    source: Any, default_levels: tuple[float, ...], default_decimals: int
) -> tuple[RatingConfigDict, bool]:
    if not isinstance(source, dict):
        source = {}
    return read_rating_config_dict(source, default_levels, default_decimals)


@dataclass(frozen=True, slots=True)
class RatingConfig:
    """Configuration for how to rate one stat"""

    levels: tuple[float, ...]
    decimals: int

    def __post_init__(self) -> None:
        """Validate parameters"""
        if self.decimals < 0:
            raise ValueError(f"Invalid value for {self.decimals=}")

    @classmethod
    def from_dict(cls, source: RatingConfigDict) -> Self:
        return cls(levels=source["levels"], decimals=source["decimals"])

    def to_dict(self) -> RatingConfigDict:
        return {"type": "level_based", "levels": self.levels, "decimals": self.decimals}


class RatingConfigCollectionDict(TypedDict):
    """Dict representing a RatingConfigCollection"""

    stars: RatingConfigDict
    fkdr: RatingConfigDict
    wlr: RatingConfigDict
    winstreak: RatingConfigDict


def read_rating_config_collection_dict(
    source: Mapping[str, Any]
) -> tuple[RatingConfigCollectionDict, bool]:
    """Read a RatingConfigCollectionDict from the source mapping"""
    any_source_updated = False

    stars, source_updated = safe_read_rating_config_dict(
        source.get("stars", None), default_levels=STARS_LEVELS, default_decimals=2
    )
    any_source_updated |= source_updated

    fkdr, source_updated = safe_read_rating_config_dict(
        source.get("fkdr", None), default_levels=FKDR_LEVELS, default_decimals=2
    )
    any_source_updated |= source_updated

    wlr, source_updated = safe_read_rating_config_dict(
        source.get("wlr", None), default_levels=WLR_LEVELS, default_decimals=2
    )
    any_source_updated |= source_updated

    winstreak, source_updated = safe_read_rating_config_dict(
        source.get("winstreak", None),
        default_levels=WINSTREAK_LEVELS,
        default_decimals=2,
    )
    any_source_updated |= source_updated

    return {
        "stars": stars,
        "fkdr": fkdr,
        "wlr": wlr,
        "winstreak": winstreak,
    }, source_updated


def safe_read_rating_config_collection_dict(
    source: Any,
) -> tuple[RatingConfigCollectionDict, bool]:
    if not isinstance(source, dict):
        source = {}
    return read_rating_config_collection_dict(source)


@dataclass(frozen=True, slots=True)
class RatingConfigCollection:
    """RatingConfig instances for all stats"""

    stars: RatingConfig
    fkdr: RatingConfig
    wlr: RatingConfig
    winstreak: RatingConfig

    @classmethod
    def from_dict(cls, source: RatingConfigCollectionDict) -> Self:
        return cls(
            stars=RatingConfig.from_dict(source["stars"]),
            fkdr=RatingConfig.from_dict(source["fkdr"]),
            wlr=RatingConfig.from_dict(source["wlr"]),
            winstreak=RatingConfig.from_dict(source["winstreak"]),
        )

    def to_dict(self) -> RatingConfigCollectionDict:
        return {
            "stars": self.stars.to_dict(),
            "fkdr": self.fkdr.to_dict(),
            "wlr": self.wlr.to_dict(),
            "winstreak": self.winstreak.to_dict(),
        }
