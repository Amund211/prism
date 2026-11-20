#!/bin/sh
# C2 round 5: B reader, synth v3 (heads, ping bars, hearts, ghost text, 10 % negative rows).
# Three nets on the same 400k data: CRNN (as tok_d400k_e8), wider CRNN, CRNN + 2 transformer blocks.
# Re-runnable: skips finished steps; training resumes from its .ckpt.
cd /home/amund/git/overlay/tabcap-tablist/lab || exit 1
L=results/c2/logs
R=results/c2

train() {  # name args...
  n=$1; shift
  [ -f $R/$n.onnx ] && return
  uv run python c2_train.py $n v3_s4,v3_s5 -1 8 --tokens --threads 4 "$@" >> $L/$n.log 2>&1
}

[ -f $R/v3_s4.pkl ] || uv run python c2_gen.py v3_s4 200000 0.6 hard 3 4 v3 > $L/gen_v3_s4.log 2>&1 &
[ -f $R/v3_s5.pkl ] || uv run python c2_gen.py v3_s5 200000 0.6 hard 3 5 v3 > $L/gen_v3_s5.log 2>&1 &
wait
train v3_crnn --width 1.5 --depth 4 &
train v3_crnn_w2 --width 2.0 --depth 4 &
train v3_tf --width 1.5 --depth 4 --tf 2 &
wait
for m in v3_crnn v3_crnn_w2 v3_tf; do
  [ -f results/tl/cache_c2_$m.pkl ] && continue
  TL_MODEL=c2/$m TL_CACHE=_c2_$m uv run python tl_cache.py -j 6 > $L/cache_$m.log 2>&1
done
echo done > $L/ROUND5_DONE
