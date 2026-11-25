"""Front step of the tab-list reader: find the tab rows, parse them, cut the
name / row crops for the model.

Port of the lab front (branch tabcap-front-split, lab/). Module map:
tl_front -> front, j3_grid -> slot, front_regions -> regions, grid3 -> grid,
ping_grid -> ping, common -> parse; the other modules keep their names.

Use: front(rgb) -> (finder, tab, prows); regions_of(rgb, prows, tab.k);
norm_crop(rgb, region.prow.row.y, x0, x1, tab.k) per name / row.
"""

from prism.overlay.tabcap.reader.front.front import clean, front, valid
from prism.overlay.tabcap.reader.front.regions import (
    H,
    NameRegion,
    norm_crop,
    regions_of,
)

__all__ = ["H", "NameRegion", "clean", "front", "norm_crop", "regions_of", "valid"]
