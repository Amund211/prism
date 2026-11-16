"""E1: Tesseract (psm 7) per row name crop + fuzzy match + Hungarian."""

import numpy as np
import pytesseract
from PIL import Image, ImageFilter

from common import parse
from e_ocrcommon import candidates, match, name_crop

CFG = "--psm 7 --oem 1 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_"
SCALE = 5
BLUR = 0.0
MAX_COST, MARGIN = 0.45, 0.15


def ocr(img: np.ndarray, blur: float | None = None) -> str:
    im = Image.fromarray(img)
    b = BLUR if blur is None else blur
    if b:
        im = im.filter(ImageFilter.GaussianBlur(b))
    return pytesseract.image_to_string(im, config=CFG).strip().replace(" ", "")


def read_texts(rgb: np.ndarray, scale: int = SCALE, blur: float = BLUR) -> tuple[list[str], list[str | None]]:
    _, prows = parse(rgb)
    cand = candidates(prows)
    return [ocr(name_crop(p, scale), blur) for p in cand], [p.team for p in cand]


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    texts, teams = read_texts(rgb)
    return match(texts, teams, known, MAX_COST, MARGIN)
