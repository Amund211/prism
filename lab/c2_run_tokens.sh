#!/bin/sh
# C2 round 4: B reader, team tokens. Same data seeds (2, 3) and net as sc_d400k_e8,
# so the only change is the team token in place of the letter.
# Re-runnable: skips finished steps; training resumes from its .ckpt.
cd /home/amund/git/overlay/tabcap-tablist/lab || exit 1
L=results/c2/logs
R=results/c2
[ -f $R/tok_s2.pkl ] || uv run python c2_gen.py tok_s2 200000 0.5 hard 3 2 tokens > $L/gen_tok_s2.log 2>&1 &
[ -f $R/tok_s3.pkl ] || uv run python c2_gen.py tok_s3 200000 0.5 hard 3 3 tokens > $L/gen_tok_s3.log 2>&1 &
wait
[ -f $R/tok_d400k_e8.onnx ] || uv run python c2_train.py tok_d400k_e8 tok_s2,tok_s3 -1 8 --width 1.5 --depth 4 --tokens --threads 12 >> $L/tok_d400k_e8.log 2>&1
[ -f results/tl/cache_c2_tok_d400k_e8.pkl ] || TL_MODEL=c2/tok_d400k_e8 TL_CACHE=_c2_tok_d400k_e8 uv run python tl_cache.py -j 6 > $L/cache_tok_d400k_e8.log 2>&1
echo done > $L/ROUND4_DONE
