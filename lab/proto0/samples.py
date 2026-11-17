"""Where the prototype's old screenshots + labels.json are. They are not in
git (user screenshots; the same images are now in the bucket fixtures).
Default: the prototype plan folder. Override: TABCAP_PROTO_SAMPLES."""

import os
from pathlib import Path

SAMPLES = Path(
    os.environ.get(
        "TABCAP_PROTO_SAMPLES",
        "~/git/overlay/plans/2026-11-02-tab-screenshot-prototype-prism/samples",
    )
).expanduser()
