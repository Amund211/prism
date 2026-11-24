# tabcap-train

Training code for the tabcap row reader model (`rk4_all`): synthetic,
composite and real row sets, and the CRNN / transformer CTC net. Own uv
project; it uses the reader front step from prism (`prism.overlay.tabcap.reader.front`).
Moved from the lab (branch `tabcap-front-split`); module names are kept, so
lab logs and notes still match.

## Setup

```
uv sync --group train   # torch (CPU) + onnx
```

## Inputs (env vars)

| Var | What | Needed by |
|---|---|---|
| `TABCAP_RESOURCE_PACKS` | Font bank dir: `fonts/`, `README.md`, `vanilla/1.8.9/assets/minecraft/textures/{font/ascii.png,gui/icons.png}`. **Private** (font licences) | all sets |
| `TABCAP_NAMES` | Real player names, one per line. **Private** | `v3n`, `v3k`, `comp`, `compk` sets |
| `PRISM_TEST_FIXTURES_DIR` | Fixture root (same as the prism tests; default `../tests/data/fixtures`): `tabcap_fixtures_<v>/` (train split only), `tabcap_synth_calib_2026-11-21/` | `c2_real`, `c2_comp` |
| `TABCAP_RESULTS` | Out dir (default `results/`, git-ignored). `c2_real` also reads `tl/cache_c2_v3_tf.pkl` (private) from it | all |

Private inputs live in a private store, never in this repo.

## Modules

| Module | What |
|---|---|
| `c2_gen.py` | Make a set: `c2_gen.py NAME N ROW_FRAC KDIST VANILLA_W SEED MODE` -> `c2/NAME.pkl`. Deterministic |
| `c2_synth.py` | Synthetic rows and name crops; charsets with team / kind tokens |
| `c2_comp.py` | Composite rows: synth tab list on real train backgrounds, cut by the front step. Needs `synth/` (generator; not moved yet) |
| `c2_real.py` | Real rows from the train fixtures (`c2_real.py kinds`) |
| `c2_train.py` | Train and export to ONNX (`--help`) |
| `i4_synth.py`, `g_bank.py` | Font render, random names, font bank |
| `data.py` | Train fixtures (test split is never read) |
| `paths.py` | The env vars above |
