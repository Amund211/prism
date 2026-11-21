#!/bin/sh
# C2 round 8: composite rows (c2_comp.py: synth tab list on real train-game plain shots,
# rows found by our front step), all on fixtures 2026-11-21. Starts after c2_run_fx1121.sh.
# - cf: fine-tune of v3n_tf on 50k v3n + 50k composite rows (4 epochs, lr 1e-3)
# - cs: control, the same fine-tune on 100k v3n rows only
# - v3c_tf: new base model as v3n_tf, data v3n_s8 + comp_s1 (200k + 200k), 8 epochs
# Re-runnable: skips finished steps; training resumes from its .ckpt.
cd /home/amund/git/overlay/tabcap-tablist/lab || exit 1
L=results/c2/logs
R=results/c2
T=results/tl
until [ -f $L/FX1121_DONE ]; do sleep 60; done

train() {  # name data epochs threads args...
  n=$1; d=$2; e=$3; t=$4; shift 4
  [ -f $R/$n.onnx ] && return
  uv run python c2_train.py $n $d -1 $e --tokens --threads $t --width 1.5 --depth 4 --tf 2 "$@" >> $L/$n.log 2>&1
}

cache() {
  [ -f $T/cache_c2_$1.pkl ] && return
  TL_MODEL=c2/$1 TL_CACHE=_c2_$1 uv run python tl_cache.py -j 3 > $L/cache_$1.log 2>&1
}

[ -f $R/comp_s1.pkl ] || uv run python c2_gen.py comp_s1 200000 0.6 hard 3 11 comp > $L/gen_comp_s1.log 2>&1
[ -f $R/comp_s2.pkl ] || uv run python c2_gen.py comp_s2 50000 0.6 hard 3 12 comp > $L/gen_comp_s2.log 2>&1

(train v3c_tf v3n_s8,comp_s1 8 6; cache v3c_tf) &
(train cf v3n_s8 4 3 --init v3n_tf --lr 1e-3 --limit 50000 --extra comp_s2:1; cache cf) &
(train cs v3n_s8 4 3 --init v3n_tf --lr 1e-3 --limit 100000; cache cs) &
wait
echo done > $L/ROUND8_DONE
