#!/bin/sh
# C2 round 8b: as c2_run_comp.sh, with the fixed composite rows (gray spectator /
# respawning rows with no letter and no token; round 8 had gray names only with the
# gray letter, so its models gave the gray token to no-team rows: 49 wrong snap teams).
cd /home/amund/git/overlay/tabcap-tablist/lab || exit 1
L=results/c2/logs
R=results/c2
T=results/tl

train() {  # name data epochs threads args...
  n=$1; d=$2; e=$3; t=$4; shift 4
  [ -f $R/$n.onnx ] && return
  uv run python c2_train.py $n $d -1 $e --tokens --threads $t --width 1.5 --depth 4 --tf 2 "$@" >> $L/$n.log 2>&1
}

cache() {
  [ -f $T/cache_c2_$1.pkl ] && return
  TL_MODEL=c2/$1 TL_CACHE=_c2_$1 uv run python tl_cache.py -j 3 > $L/cache_$1.log 2>&1
}

[ -f $R/comp2_s1.pkl ] || uv run python c2_gen.py comp2_s1 200000 0.6 hard 3 11 comp > $L/gen_comp2_s1.log 2>&1
[ -f $R/comp2_s2.pkl ] || uv run python c2_gen.py comp2_s2 50000 0.6 hard 3 12 comp > $L/gen_comp2_s2.log 2>&1

(train v3c2_tf v3n_s8,comp2_s1 8 8; cache v3c2_tf) &
(train cf2 v3n_s8 4 4 --init v3n_tf --lr 1e-3 --limit 50000 --extra comp2_s2:1; cache cf2) &
wait
echo done > $L/ROUND8B_DONE
