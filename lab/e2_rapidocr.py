"""E2: RapidOCR (PP-OCRv6 rec over ONNX) on row name crops; fuzzy match.
read_teams: rec only on parser crops. read_teams_panel (E2b): det + rec on
the whole tab-panel crop, lines matched to parsed rows by y."""

from functools import cache

import numpy as np

from common import parse
from e_ocrcommon import candidates, match, name_crop

MAX_COST, MARGIN = 0.45, 0.1


@cache
def engine():  # type: ignore[no-untyped-def]
    import onnxruntime
    from rapidocr import RapidOCR

    onnxruntime.disable_telemetry_events()
    return RapidOCR(
        params={
            "Global.log_level": "error",
            "EngineConfig.onnxruntime.intra_op_num_threads": 1,
            "EngineConfig.onnxruntime.inter_op_num_threads": 1,
        }
    )


def ocr(img: np.ndarray) -> str:
    rgb = np.repeat(img[:, :, None], 3, axis=2)
    r = engine()(rgb, use_det=False, use_cls=False, use_rec=True)
    t = "".join(r.txts or ())
    return "".join(c for c in t if c.isalnum() or c == "_")


def read_texts(rgb: np.ndarray, scale: int = 5) -> tuple[list[str], list[str | None]]:
    _, prows = parse(rgb)
    cand = candidates(prows)
    return [ocr(name_crop(p, scale, pad=8)) for p in cand], [p.team for p in cand]


def read_teams(rgb: np.ndarray, known: list[str]) -> dict[str, str]:
    texts, teams = read_texts(rgb)
    return match(texts, teams, known, MAX_COST, MARGIN)
