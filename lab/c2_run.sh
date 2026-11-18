#!/bin/sh
# C2 round 1: data, then 5 full-font models (3 + 2 in parallel, 4 threads each),
# then read caches for each. Logs: results/c2/logs/
cd /home/amund/git/overlay/tabcap-tablist/lab || exit 1
mkdir -p results/c2/logs
L=results/c2/logs
set -x
# reproducibility: the i4 dataset again (same seeds)
uv run python i4_gen.py 100000 > $L/gen_i4.log 2>&1
sha256sum results/i4/data_orig.pkl results/i4/data.pkl > $L/i4_hash.txt
cmp results/i4/folds.json results/i4/folds_orig.json >> $L/i4_hash.txt 2>&1
uv run python c2_gen.py name_hard 200000 0.0 hard 3 1 > $L/gen_name_hard.log 2>&1
uv run python c2_gen.py mix 200000 0.5 hard 3 2 > $L/gen_mix.log 2>&1

uv run python c2_train.py i4r_s0 i4 -1 8 --seed 0 > $L/i4r_s0.log 2>&1 &
uv run python c2_train.py i4r_s1 i4 -1 8 --seed 1 > $L/i4r_s1.log 2>&1 &
uv run python c2_train.py name_hard name_hard -1 8 > $L/name_hard.log 2>&1 &
wait
uv run python c2_train.py mix mix -1 8 --threads 6 > $L/mix.log 2>&1 &
uv run python c2_train.py mix_wide mix -1 8 --width 1.5 --depth 4 --threads 6 > $L/mix_wide.log 2>&1 &
wait
for m in i4r_s0 i4r_s1 name_hard mix mix_wide; do
  TL_MODEL=c2/$m TL_CACHE=_c2_$m uv run python tl_cache.py -j 6 > $L/cache_$m.log 2>&1
done
echo done > $L/ROUND1_DONE
