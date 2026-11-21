#!/bin/sh
# C2 round 6 (night run), from the Round 5 winner v3_tf (CRNN + 2 transformer blocks).
# 1. v3_tf4: 4 transformer blocks, same data (more capacity where Round 5 gained).
# 2. v3_tf_d800k_e4: 2 blocks, 2x data (seeds 6, 7), 4 epochs (same steps): data vs compute for the tf.
# 3. rf_0..2: fine-tune v3_tf on real row crops (c2_real.py, 3 folds by font pack) + 100k synth;
#    rs: the same fine-tune without real rows (control).
# Re-runnable: skips finished steps; training resumes from its .ckpt.
cd /home/amund/git/overlay/tabcap-tablist/lab || exit 1
L=results/c2/logs
R=results/c2

train() {  # name data epochs args...
  n=$1; d=$2; e=$3; shift 3
  [ -f $R/$n.onnx ] && return
  uv run python c2_train.py $n $d -1 $e --tokens --threads 4 --width 1.5 --depth 4 "$@" >> $L/$n.log 2>&1
}

cache() {  # model [folds json]
  [ -f results/tl/cache_c2_$1.pkl ] && return
  if [ -n "$2" ]; then
    TL_FOLDS=$2 TL_MODEL=c2/$1 TL_CACHE=_c2_$1 uv run python tl_cache.py -j 4 > $L/cache_$1.log 2>&1
  else
    TL_MODEL=c2/$1 TL_CACHE=_c2_$1 uv run python tl_cache.py -j 4 > $L/cache_$1.log 2>&1
  fi
}

[ -f $R/real_f2.pkl ] || uv run python c2_real.py > $L/real.log 2>&1

(train v3_tf4 v3_s4,v3_s5 8 --tf 4; cache v3_tf4) &

(
  [ -f $R/v3_s6.pkl ] || uv run python c2_gen.py v3_s6 200000 0.6 hard 3 6 v3 > $L/gen_v3_s6.log 2>&1 &
  [ -f $R/v3_s7.pkl ] || uv run python c2_gen.py v3_s7 200000 0.6 hard 3 7 v3 > $L/gen_v3_s7.log 2>&1 &
  wait
  train v3_tf_d800k_e4 v3_s4,v3_s5,v3_s6,v3_s7 4 --tf 2
  cache v3_tf_d800k_e4
) &

(
  for f in 0 1 2; do
    train rf_$f v3_s4 4 --tf 2 --init v3_tf --lr 1e-3 --limit 100000 --extra real_f$f:8
  done
  cache rf_ $R/real_folds.json
  train rs v3_s4 4 --tf 2 --init v3_tf --lr 1e-3 --limit 100000
  cache rs
) &

wait
echo done > $L/ROUND6_DONE
