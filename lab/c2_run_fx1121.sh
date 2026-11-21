#!/bin/sh
# Fixtures tabcap_fixtures_2026-11-21 (train 189 -> 206): score the models again, build the real
# rows again (c2_real.py), then the real-row fine-tune of v3n_tf (rn_0..2, new folds).
# Old caches / real rows go to */fx1115/. Old fold models (rf_, rh_) keep their folds; new images
# get the fold of their pack (c2_folds_extend.py). Re-runnable: skips finished steps.
cd /home/amund/git/overlay/tabcap-tablist/lab || exit 1
L=results/c2/logs
R=results/c2
T=results/tl
mkdir -p $T/fx1115 $R/fx1115
if [ ! -f $R/fx1115/real_folds.json ]; then
  mv $T/cache_c2_*.pkl $T/fx1115/
  mv $R/real_f*.pkl $R/real_folds.json $R/fx1115/
fi
[ -f $R/old_folds_ext.json ] || uv run python c2_folds_extend.py $R/fx1115/real_folds.json $R/old_folds_ext.json

cache() {  # model [folds json]
  [ -f $T/cache_c2_$1.pkl ] && return
  if [ -n "$2" ]; then
    TL_FOLDS=$2 TL_MODEL=c2/$1 TL_CACHE=_c2_$1 uv run python tl_cache.py -j 3 > $L/fx_cache_$1.log 2>&1
  else
    TL_MODEL=c2/$1 TL_CACHE=_c2_$1 uv run python tl_cache.py -j 3 > $L/fx_cache_$1.log 2>&1
  fi
}

cache v3_tf
[ -f $R/real_folds.json ] || uv run python c2_real.py > $L/fx_real.log 2>&1
(
  for f in 0 1 2; do
    [ -f $R/rn_$f.onnx ] || uv run python c2_train.py rn_$f v3n_s8 -1 4 --tokens --threads 2 --width 1.5 --depth 4 --tf 2 \
      --init v3n_tf --lr 1e-3 --limit 100000 --extra real_f$f:8 >> $L/rn_$f.log 2>&1 &
  done
  wait
  cache rn_ $R/real_folds.json
) &
cache v3n_tf
cache sc_d400k_e8
cache rs
cache rf_ $R/old_folds_ext.json
cache rh_ $R/old_folds_ext.json
cache v3_tf_d800k_e4
wait
echo done > $L/FX1121_DONE
