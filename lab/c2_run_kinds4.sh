#!/bin/sh
# C2 round 11: the round 9 kinds recipe (kf, rk_) from the new base v3c3_tf in place of v3n_tf.
# kf4 = v3c3_tf (output layer grown) + 50k v3k + 50k compk rows; rk4_0..2 = kf4 + realk rows.
cd /home/amund/git/overlay/tabcap-tablist/lab || exit 1
L=results/c2/logs
R=results/c2
T=results/tl

train() {  # name data epochs threads args...
  n=$1; d=$2; e=$3; t=$4; shift 4
  [ -f $R/$n.onnx ] && return
  uv run python c2_train.py $n $d -1 $e --tokens --kinds --threads $t --width 1.5 --depth 4 --tf 2 "$@" >> $L/$n.log 2>&1
}

cache() {  # model [folds json]
  [ -f $T/cache_c2_$1.pkl ] && return
  if [ -n "$2" ]; then
    TL_FOLDS=$2 TL_MODEL=c2/$1 TL_CACHE=_c2_$1 uv run python tl_cache.py -j 3 > $L/cache_$1.log 2>&1
  else
    TL_MODEL=c2/$1 TL_CACHE=_c2_$1 uv run python tl_cache.py -j 3 > $L/cache_$1.log 2>&1
  fi
}

train kf4 v3k_s1 4 12 --init v3c3_tf --lr 1e-3 --limit 50000 --extra compk_s1:1
cache kf4
for f in 0 1 2; do
  train rk4_$f v3k_s1 4 4 --init kf4 --lr 1e-3 --limit 100000 --extra realk_f$f:8 &
done
wait
cache rk4_ $R/real_folds.json
echo done > $L/ROUND11_DONE
