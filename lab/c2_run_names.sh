#!/bin/sh
# C2 round 7. A: synth v3n (v3 + 70 % real Flashlight names, fixture names removed) -> v3n_tf
#   (as v3_tf), then the real-row fine-tune rn_0..2 (as rf_). B: learning curve: rh_0..2 =
#   rf_ with the real rows of half the images (rep 16, so the same real share of samples).
# Re-runnable: skips finished steps; training resumes from its .ckpt.
cd /home/amund/git/overlay/tabcap-tablist/lab || exit 1
L=results/c2/logs
R=results/c2

train() {  # name data epochs threads args...
  n=$1; d=$2; e=$3; t=$4; shift 4
  [ -f $R/$n.onnx ] && return
  uv run python c2_train.py $n $d -1 $e --tokens --threads $t --width 1.5 --depth 4 --tf 2 "$@" >> $L/$n.log 2>&1
}

cache() {  # model [folds json]
  [ -f results/tl/cache_c2_$1.pkl ] && return
  if [ -n "$2" ]; then
    TL_FOLDS=$2 TL_MODEL=c2/$1 TL_CACHE=_c2_$1 uv run python tl_cache.py -j 4 > $L/cache_$1.log 2>&1
  else
    TL_MODEL=c2/$1 TL_CACHE=_c2_$1 uv run python tl_cache.py -j 4 > $L/cache_$1.log 2>&1
  fi
}

(
  [ -f $R/v3n_s8.pkl ] || uv run python c2_gen.py v3n_s8 200000 0.6 hard 3 8 v3n > $L/gen_v3n_s8.log 2>&1 &
  [ -f $R/v3n_s9.pkl ] || uv run python c2_gen.py v3n_s9 200000 0.6 hard 3 9 v3n > $L/gen_v3n_s9.log 2>&1 &
  wait
  train v3n_tf v3n_s8,v3n_s9 8 6
  cache v3n_tf
  # rn_0..2 (real-row fine-tune of v3n_tf) waits for the new fixtures version: then
  # c2_real.py again, and: train rn_$f v3n_s8 4 4 --init v3n_tf --lr 1e-3 --limit 100000 --extra real_f$f:8
) &

(
  for f in 0 1 2; do
    train rh_$f v3_s4 4 2 --init v3_tf --lr 1e-3 --limit 100000 --extra real_f${f}_h:16 &
  done
  wait
  cache rh_ $R/real_folds.json
) &

wait
echo done > $L/ROUND7_DONE
