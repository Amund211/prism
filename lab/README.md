# Tabcap team-reader lab

Experiments for reading the team of each player from a tab-list
screenshot (Hypixel Bed Wars). Not prism code. **Train split only**:
`data.py` asserts it; do not run on test images.

Images and labels: `~/git/overlay/test-fixtures/<version>/` (manifest
`prism/tests/data/tabcap_fixtures.json`, weights `tabcap_weights.json`).

## Run

```
uv run python bench.py <module> -j 3 --groups   # score, writes results/<module>.json
uv run python mybench.py <module> -j 4          # same + per-font lines and a ref diff
```

A bench module has `read_teams(rgb, known) -> {name: team}`. Scores:
correct / wrong / unknown % of label rows, also weighted by how common the
setup is (`w_*`). Target: high correct with 0 wrong.

## Best fast pipeline: `j4_slotping` (train: 90.7 %, 92.3 weighted, 0 wrong, ~104 ms)

```
RGB ─┬─ 1a grid3.find_grid      cell grid (row cells: vanilla, Forge, packs)
     ├─ 1b ping_grid.find_ping  ping icons (no cells: Lunar)
     │      -> Grid(k, tops, cols, weak)
     │   2  row adapter          j3_slot.grid_parse (text range x0+9k .. x1-11k)
     ├─ 1c rows.find_tab        old text-ladder finder (fallback)
     │      -> Tab(k, rows, shadow mask)
     │   3  common.parse         -> PRow(row, letter, name, team, words)
     │   4  j3_slot.slot_team    team from the letter slot when parse has none;
     │                           mask bgmask.bg_mask (cells) / lunar_mask (ping rows)
     │   5  g2 + d3 + c5 vote    j3_slot.match (h_common, h4_union)
     └──────> {name: team}
```

The first finder (1a, 1b, 1c) whose parse gives >= 2 rows with a team wins.

| Part | Module | Alone |
|---|---|---|
| Cell grid | `grid3.py` | `python grid3.py [substr]`: exact row count per image |
| Ping finder | `ping_grid.py` | `python ping_grid.py [substr]`: exact row count; `ping_dbg.py`: all candidates |
| Old finder | `rows.py`, `textmask.py` | `pipeline_check.py` |
| Parse | `common.py`, `rowparse.py` | `dbg_parse.py` |
| Letter slot | `j3_slot.py`, `bgmask.py`, `lunar_mask.py` | any Grid-like object (`.k .tops .cols .weak`); `ping_stage.py` prints reasons on Lunar |
| Matchers | `h_common.py` (g2), `h4_union.py` (d3, c5), `g_bank.py`, `d_core.py`, `c5_fast.py` | on any parse |
| Oracle ladder | `oracle.py`, `budget.py` | any pipeline that exposes `grid_parse(rgb) -> (grid, tab, prows)` |

Key facts the parts use:

- Vanilla row cell = panel x 0.4375 + 32 (`0x20FFFFFF` over `0x80000000`),
  8 GUI px high, pitch 9: an up / down edge pair on every channel
  (`grid3`). Cell = separator x 0.875 + 32 (`bgmask`).
- Lunar draws no cells. The ping icon is an opaque texture, so it repeats
  exactly at pitch 9k (`ping_grid`). Background of a row pixel = the
  empty gap row above / below, no colour change (`lunar_mask`). Lunar
  users have a moon icon (8k) before the team letter; the slot is retried
  9k later.
- Glyphs use GUI rows 0-6, shadow 1-7, GUI row 8 is empty.

## Bench modules (train, correct / weighted)

| Module | What | Score |
|---|---|---|
| `h4_union` | find_tab + g2/d3/c5 vote | 80.8 / 81.5 |
| `j2_bg` (`J_MASK=shadow`) | grid, find_tab | 86.8 / 87.8 |
| `j3_ping` (`J3_STAGES=gpf`) | grid, ping, find_tab | 87.1 / 88.9 |
| `j3_slot` | grid + letter slot, find_tab | 90.2 / 90.4 |
| **`j4_slotping`** | grid + slot, ping + Lunar slot, find_tab | **90.7 / 92.3** |
| `i2_cascade_v` | OCR cascade + word spotting (slow, ~1-5 s) | 93.2 / 94.2, 5 wrong |

Older families (a-i): see the module docstrings.

## Grid prototypes (moved from the plan folder)

| Module | What | Train |
|---|---|---|
| `j1_grid` | grid rows, crude adapter (one column, cell range), h4 vote | 81.2 % |
| `k1_shape` (`run_k1.py k1_shape bg`) | word-shape code matcher (tall / x-height / descender per glyph), no font data; `python k1_shape.py uniq` = code uniqueness, no images | 62.1 % alone |
| `heads.py`, `heads_union.py` | head fingerprints (8x8 skin face per row); bank from labels, so an upper bound, not a reader. Cache in `results/heads.pkl` | 86.7 % of rows |
| `bestof.py A.json B.json` | per image, the result with more answers | |
| `vote2.py A.json B.json` | per-name vote of two results | |

## Tab-list reader (open set, no known names; 2026-11-17)

Reads every player name and team from the image, without `known`. Notes:
`plans/2026-11-17-tabcap-tablist-prism/`.

| File | What |
|---|---|
| `tbench.py <module>` | bench for `read_tab(rgb) -> [(name, team)]`: exact name, name + team, bad reads, read precision, snap-to-known score. Writes `results/tl/` |
| `tl_front.py` | j4 finder chain (grid -> ping -> old) and name checks |
| `t1_crnn.py` | j4 front + i4 CRNN greedy read per name region |
| `t4_selffont.py` | T1 + self-learned glyphs to fix / reject chars (did not help) |
| `tl_cache.py` | CRNN reads (name crop, row crop, char probs; `TL_OCR`: + RapidOCR) per image -> `results/tl/cache*.pkl` (`run_loo_cache.sh`, `run_ocr_cache.sh`) |
| `tl_sweep.py [policy...] [--cache=_loo] [--extra]` | post-read policies on a cache (best: `V1`, `V2`) |
| `tl_hybrid.py [policy] [--cache=_loo]` | hybrid: drop one name from `known`, is it read as a new name? false new reads per image |
| `tl_peek.py`, `tl_show.py`, `tl_ocrdiff.py` | debug views |

Decode and fusion tries (2026-11-18), on a log-prob cache:

| File | What |
|---|---|
| `u_cache.py` | as `tl_cache`, plus CTC log-probs of the name crop, row crop and 5 shifted name crops -> `results/tl/ucache*.pkl` |
| `u_decode.py` | CTC prefix beam, N-best posterior, rescoring over crops |
| `u_exp.py` | decode variants (greedy, beam, TTA, posterior conf) under X2 + tau sweep |
| `u_snap.py` | snap costs: Levenshtein, CTC, min, likelihood ratio |
| `u_union.py` | **snap + open-set reads in one list** (best: 94.8 % full) |
| `u_ceiling.py`, `u_choice.py`, `u_noreg.py`, `u_wteam.py`, `u_peek.py` | where misses come from; name vs row choice |

### B reader: model reads the whole row (2026-11-19 to 11-22)

CRNN-CTC + 2 transformer blocks reads "team-token name health" from the
row crop (`c2_*.py`; notes: `b-reader.md` in the plan folder).

**Best: `rc4_`** (train, fixtures 2026-11-21, policy B4): 95.2 % full,
93.4 weighted, 43 bad reads, 0 wrong snap teams. Recipe:

1. `c2_run_comp3.sh`: composite rows (`c2_comp.py`: the synth generator on
   real plain shots of train games) -> base `v3c3_tf` (synth + composite
   1:1, 8 epochs).
2. `c2_run_rc4.sh`: `cf4` (+ 50k composite), then `rc4_0..2` (+ real rows
   x8 from `c2_real.py`, folds by font pack).

Findings: composite rows help names; composite rows must match the real
row kinds (respawning rows: gray, no letter, with health), else the token
team is wrong; the real-row fine-tune removes the wrong teams. Row kind
tokens (⑨ respawning, ⑩ spectator: `--kinds`, `c2_run_kinds*.sh`) work,
but cost a little on names. `TL_SPLIT=test` (`data.py`) and `TL_OUT`
(`tl_cache.py`) are for final test scores only; those scores are never
written to files.

## `proto0/`: the first prototype (2026-11-02)

The first team reader (`tabteams`, `tabsoft`, `tablearn`, `tablayout`,
`glyphs`); `prism/src/prism/overlay/tabcap/teams/` grew from it. It reads
the old screenshots in `proto0/samples.py` (`TABCAP_PROTO_SAMPLES`; not
in git). **Those samples are not split**: some are now test fixtures, so
use `evaluate.py` only to compare with old numbers, never to tune.

## Extra dependencies

- `i4_train.py` needs torch (not in `pyproject.toml`). The trained
  models are in `results/i4/` (gitignored); re-run `i4_gen.py` and
  `i4_train.py` on a fresh checkout before the `i4_*` benches.
- `e1_tesseract` needs the tesseract binary on PATH. Full notes, numbers and
failed tries are in the plan folder
`plans/2026-11-16-tabcap-team-algos-prism/` (not in git; start at
`pipeline-map.md`).
