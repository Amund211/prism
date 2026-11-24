"""The text model rk4_all (ONNX): one 20 px row crop in, CTC logits out.

The sidecar rk4_all.json holds the SHA-256, charset, crop rules, train args
and bench numbers of the model file.
"""

import functools
import os
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from prism.overlay.tabcap.reader.decode import decode
from prism.overlay.tabcap.reader.front.guiscale import Array

if TYPE_CHECKING:  # pragma: nocover
    import onnxruntime  # type: ignore[import-untyped]

MODEL = Path(__file__).with_name("rk4_all.onnx")
SIDECAR = Path(__file__).with_name("rk4_all.json")


@functools.cache
def session() -> "onnxruntime.InferenceSession":
    # onnxruntime >= 1.32 uploads telemetry to Microsoft unless this is set
    # before the import. disable_telemetry_events() does not stop it.
    os.environ["ORT_DISABLE_TELEMETRY"] = "1"
    # Lazy: onnxruntime is not in the macOS build
    import onnxruntime

    options = onnxruntime.SessionOptions()
    # One thread, so the reader does not take every core from the game
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    return onnxruntime.InferenceSession(
        str(MODEL), options, providers=["CPUExecutionProvider"]
    )


def logits(crop: Array) -> Array:
    """C x T logits of one 20 x W x 3 uint8 RGB crop"""
    x = (crop.astype(np.float32) / 255).transpose(2, 0, 1)[None]
    out: Array = session().run(None, {"x": x})[0][0]
    return out


def read(crop: Array) -> str:
    return decode(logits(crop))
