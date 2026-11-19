#!/bin/sh
# C2 round 3: data vs compute. mix_wide net (width 1.5, depth 4), all fonts.
# Equal compute (0.8 M sample-epochs): d25k_e32, d50k_e16, d100k_e8.
# Equal compute (1.6 M): d100k_e16 vs mix_wide (200k x 8, round 1).
# Equal compute (3.2 M): d200k_e16 (more steps) vs d400k_e8 (more data).
# Re-runnable: skips finished steps; training resumes from its .ckpt.
cd /home/amund/git/overlay/tabcap-tablist/lab || exit 1
L=results/c2/logs
R=results/c2
W="--width 1.5 --depth 4"

train() {  # name threads args...
  n=$1; t=$2; shift 2
  [ -f $R/$n.onnx ] && return
  uv run python c2_train.py $n "$@" $W --threads $t >> $L/$n.log 2>&1
}

[ -f $R/mix_s3.pkl ] || uv run python c2_gen.py mix_s3 200000 0.5 hard 3 3 > $L/gen_mix_s3.log 2>&1 &
train sc_d25k_e32 3 mix -1 32 --limit 25000 &
train sc_d50k_e16 3 mix -1 16 --limit 50000 &
train sc_d100k_e8 3 mix -1 8 --limit 100000 &
train sc_d100k_e16 3 mix -1 16 --limit 100000 &
wait
train sc_d200k_e16 6 mix -1 16 &
train sc_d400k_e8 6 mix,mix_s3 -1 8 &
wait
for m in sc_d25k_e32 sc_d50k_e16 sc_d100k_e8 sc_d100k_e16 sc_d200k_e16 sc_d400k_e8; do
  [ -f results/tl/cache_c2_$m.pkl ] && continue
  TL_MODEL=c2/$m TL_CACHE=_c2_$m uv run python tl_cache.py -j 6 > $L/cache_$m.log 2>&1
done
echo done > $L/ROUND3_DONE
