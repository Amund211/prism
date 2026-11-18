#!/bin/sh
# Read caches for the round-1 models that are done (2 procs; training still runs)
cd /home/amund/git/overlay/tabcap-tablist/lab || exit 1
for m in i4r_s0 i4r_s1 name_hard; do
  TL_MODEL=c2/$m TL_CACHE=_c2_$m uv run python tl_cache.py -j 2 2>&1 | tail -1
done
