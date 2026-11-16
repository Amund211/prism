"""E1 variant: scale 4, blur 1.0 (for e_cache sweeps)"""

import e1_tesseract as e


def read_texts(rgb):  # type: ignore[no-untyped-def]
    return e.read_texts(rgb, scale=4, blur=1.0)
