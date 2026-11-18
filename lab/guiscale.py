"""GUI scales to try on an image."""

import numpy as np


def gui_ks(rgb: np.ndarray) -> range:
    """1 .. the 1.8.9 Auto scale of the image size (no scale can be larger):
    1440p Auto = 6, 4K Auto = 9. A capture larger than the window only
    widens the range."""
    h, w = rgb.shape[:2]
    return range(1, max(1, min(h // 240, w // 320)) + 1)
