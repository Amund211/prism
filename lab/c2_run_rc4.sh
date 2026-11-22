#!/bin/sh
# C2 round 10: the rc_ recipe from the new base v3c3_tf in place of v3n_tf.
# cf4 = v3c3_tf + 50k synth / 50k composite (comp3_s2, not seen by v3c3_tf), then
# rc4_0..2 = cf4 + real rows (folds by pack).
cd /home/amund/git/overlay/tabcap-tablist/lab || exit 1
L=results/c2/logs
R=results/c2
T=results/tl

train() {  # name data epochs threads args...
  n=$1; d=$2; e=$3; t=$4; shift 4
  [ -f $R/$n.onnx ] && return
  uv run python c2_train.py $n $d -1 $e --tokens --threads $t --width 1.5 --depth 4 --tf 2 "$@" >> $L/$n.log 2>&1
}

cache() {  # model [folds json]
  [ -f $T/cache_c2_$1.pkl ] && return
  if [ -n "$2" ]; then
    TL_FOLDS=$2 TL_MODEL=c2/$1 TL_CACHE=_c2_$1 uv run python tl_cache.py -j 3 > $L/cache_$1.log 2>&1
  else
    TL_MODEL=c2/$1 TL_CACHE=_c2_$1 uv run python tl_cache.py -j 3 > $L/cache_$1.log 2>&1
  fi
}

train cf4 v3n_s8 4 12 --init v3c3_tf --lr 1e-3 --limit 50000 --extra comp3_s2:1
cache cf4
for f in 0 1 2; do
  train rc4_$f v3n_s8 4 4 --init cf4 --lr 1e-3 --limit 100000 --extra real_f$f:8 &
done
wait
cache rc4_ $R/real_folds.json
echo done > $L/ROUND10_DONE
