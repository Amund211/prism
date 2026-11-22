#!/bin/sh
# C2 round 9: row kind tokens (respawning ⑨, spectator ⑩; next.md step 18). Charset CHARS_K.
# - kf: fine-tune of v3n_tf (output layer grown) on 50k v3k + 50k compk rows, 4 epochs
# - rk_0..2: kf + real rows with kind tokens (realk_f*, folds by pack), as rn_
# Data now; training after round 8c's rc_ (shares the CPU with v3c3_tf only).
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

[ -f $R/realk_f0.pkl ] || uv run python c2_real.py kinds > $L/realk.log 2>&1
[ -f $R/v3k_s1.pkl ] || uv run python c2_gen.py v3k_s1 100000 0.6 hard 3 31 v3k > $L/gen_v3k_s1.log 2>&1
[ -f $R/compk_s1.pkl ] || uv run python c2_gen.py compk_s1 50000 0.6 hard 3 32 compk > $L/gen_compk_s1.log 2>&1
until [ -f $T/cache_c2_rc_.pkl ]; do sleep 60; done

train kf v3k_s1 4 6 --init v3n_tf --lr 1e-3 --limit 50000 --extra compk_s1:1
cache kf
for f in 0 1 2; do
  train rk_$f v3k_s1 4 2 --init kf --lr 1e-3 --limit 100000 --extra realk_f$f:8 &
done
wait
cache rk_ $R/real_folds.json
echo done > $L/ROUND9_DONE
