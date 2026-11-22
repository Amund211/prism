#!/bin/sh
# C2 round 8c: composite rows fixed again: real respawning rows are gray, no letter, WITH
# health (8b had no-team rows only without health, so health -> token stayed: 48 wrong snap
# teams). cf3 (fine-tune of v3n_tf), v3c3_tf (new base), then rc_0..2 = cf3 + real rows (as rn_).
# Starts after c2_run_comp2.sh.
cd /home/amund/git/overlay/tabcap-tablist/lab || exit 1
L=results/c2/logs
R=results/c2
T=results/tl
until [ -f $L/ROUND8B_DONE ]; do sleep 60; done

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

[ -f $R/comp3_s1.pkl ] || uv run python c2_gen.py comp3_s1 200000 0.6 hard 3 21 comp > $L/gen_comp3_s1.log 2>&1
[ -f $R/comp3_s2.pkl ] || uv run python c2_gen.py comp3_s2 50000 0.6 hard 3 22 comp > $L/gen_comp3_s2.log 2>&1

(train v3c3_tf v3n_s8,comp3_s1 8 6; cache v3c3_tf) &
(
  train cf3 v3n_s8 4 6 --init v3n_tf --lr 1e-3 --limit 50000 --extra comp3_s2:1
  cache cf3
  for f in 0 1 2; do
    train rc_$f v3n_s8 4 2 --init cf3 --lr 1e-3 --limit 100000 --extra real_f$f:8 &
  done
  wait
  cache rc_ $R/real_folds.json
) &
wait
echo done > $L/ROUND8C_DONE
