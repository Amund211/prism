#!/bin/sh
# C2 round 2: leave-own-font-out versions of mix_wide (3 folds in parallel), then the loo read cache
cd /home/amund/git/overlay/tabcap-tablist/lab || exit 1
L=results/c2/logs
for i in 0 1 2; do
  uv run python c2_train.py mix_wide_loo$i mix $i 8 --width 1.5 --depth 4 --threads 4 > $L/mix_wide_loo$i.log 2>&1 &
done
wait
TL_MODEL=loo TL_LOO_PREFIX=c2/mix_wide_ TL_CACHE=_c2_mix_wide_loo uv run python tl_cache.py -j 6 > $L/cache_mix_wide_loo.log 2>&1
echo done > $L/ROUND2_DONE
